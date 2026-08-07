import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import connection, init_db
from .real_data import data_status, realtime_estimate, realtime_holdings, search_funds, sync_all, sync_fund, sync_market
from .schemas import HoldingCreate, HoldingUpdate
from .services import dashboard, generate_report, holding_rows


async def auto_sync_loop():
    await asyncio.sleep(3)
    while True:
        try:
            await asyncio.to_thread(sync_all)
        except Exception:
            pass
        await asyncio.sleep(max(settings.sync_interval_minutes, 5) * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(auto_sync_loop()) if settings.auto_sync_enabled else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AI 基金助手 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4173", "http://127.0.0.1:4173"], allow_methods=["*"], allow_headers=["*"])
market_refresh_lock = asyncio.Lock()
CN_TZ = ZoneInfo("Asia/Shanghai")


@app.get("/api/health")
def health(): return {"status": "ok", "date": date.today()}


@app.get("/api/dashboard")
def get_dashboard(): return dashboard()


@app.get("/api/holdings")
def get_holdings(): return holding_rows()


@app.post("/api/holdings", status_code=201)
async def create_holding(payload: HoldingCreate):
    sync_error = None
    try:
        await asyncio.to_thread(sync_fund, payload.fund_code)
    except Exception as exc:
        sync_error = str(exc)
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO funds(code,name,category,risk_level) VALUES(?,?,?,?)", (payload.fund_code, payload.fund_name, payload.category, payload.risk_level))
        latest = conn.execute("SELECT 1 FROM fund_navs WHERE fund_code=? LIMIT 1", (payload.fund_code,)).fetchone()
        if not latest:
            conn.execute("INSERT INTO fund_navs(fund_code,nav_date,nav,daily_change) VALUES(?,?,?,?)", (payload.fund_code, date.today().isoformat(), payload.cost_nav, 0))
        cur = conn.execute("INSERT INTO holdings(user_id,fund_code,shares,cost_nav,target_weight) VALUES(1,?,?,?,?)", (payload.fund_code, payload.shares, payload.cost_nav, payload.target_weight))
    return {"id": cur.lastrowid, "data_status": "real" if not sync_error else "pending", "sync_error": sync_error}


@app.patch("/api/holdings/{holding_id}")
def update_holding(holding_id: int, payload: HoldingUpdate):
    values = payload.model_dump(exclude_none=True)
    if not values: return {"id": holding_id}
    with connection() as conn:
        exists = conn.execute("SELECT 1 FROM holdings WHERE id=?", (holding_id,)).fetchone()
        if not exists: raise HTTPException(404, "持仓不存在")
        conn.execute(f"UPDATE holdings SET {', '.join(f'{k}=?' for k in values)} WHERE id=?", (*values.values(), holding_id))
    return {"id": holding_id}


@app.delete("/api/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int):
    with connection() as conn: conn.execute("DELETE FROM holdings WHERE id=?", (holding_id,))


@app.get("/api/funds/{code}")
def fund_detail(code: str):
    with connection() as conn:
        fund = conn.execute("SELECT * FROM funds WHERE code=?", (code,)).fetchone()
        navs = [dict(r) for r in conn.execute("SELECT nav_date,nav,daily_change,data_source,updated_at FROM fund_navs WHERE fund_code=? ORDER BY nav_date DESC LIMIT 365", (code,))]
        navs.reverse()
        positions = [dict(r) for r in conn.execute("SELECT stock_code,stock_name,weight,shares_10k,market_value_10k,report_date,data_source FROM fund_positions WHERE fund_code=? ORDER BY weight DESC LIMIT 10", (code,))]
        mapping_row = conn.execute("SELECT * FROM fund_realtime_mappings WHERE fund_code=?", (code,)).fetchone()
        mapping = dict(mapping_row) if mapping_row else None
        target_positions = []
        if mapping:
            target_positions = [dict(r) for r in conn.execute("SELECT stock_code,stock_name,weight,shares_10k,market_value_10k,report_date,data_source FROM fund_positions WHERE fund_code=? ORDER BY weight DESC LIMIT 10", (mapping["target_etf_code"],))]
    if not fund: raise HTTPException(404, "基金不存在")
    return {
        **dict(fund),
        "navs": navs,
        "top_holdings": positions,
        "position_date": positions[0]["report_date"] if positions else None,
        "target_fund": ({
            "code": mapping["target_etf_code"],
            "name": mapping["target_etf_name"],
            "exposure_ratio": mapping["exposure_ratio"],
            "source": mapping["source"],
        } if mapping else None),
        "underlying_holdings": target_positions,
        "underlying_position_date": target_positions[0]["report_date"] if target_positions else None,
    }


@app.post("/api/funds/{code}/refresh")
async def refresh(code: str):
    try: return await asyncio.to_thread(sync_fund, code)
    except Exception as exc: raise HTTPException(502, f"行情刷新失败：{exc}") from exc


@app.get("/api/search/funds")
async def fund_search(q: str):
    try: return await asyncio.to_thread(search_funds, q)
    except Exception as exc: raise HTTPException(502, f"基金搜索失败：{exc}") from exc


@app.get("/api/data/status")
def get_data_status(): return data_status()


@app.post("/api/data/sync")
async def run_data_sync():
    return await asyncio.to_thread(sync_all)


@app.get("/api/realtime/holdings")
async def get_realtime_holdings():
    try: return await asyncio.to_thread(realtime_holdings)
    except Exception as exc: raise HTTPException(502, f"盘中估值失败：{exc}") from exc


@app.get("/api/realtime/funds/{code}")
async def get_realtime_fund(code: str):
    with connection() as conn:
        holding = conn.execute("SELECT shares,cost_nav FROM holdings WHERE fund_code=? ORDER BY id LIMIT 1", (code,)).fetchone()
    if not holding: raise HTTPException(404, "尚未持有该基金")
    try: return await asyncio.to_thread(realtime_estimate, code, holding["shares"], holding["cost_nav"])
    except Exception as exc: raise HTTPException(502, f"盘中估值失败：{exc}") from exc


def market_session(now: datetime) -> tuple[str, str, bool]:
    if now.weekday() >= 5:
        return "closed", "周末休市", False
    current = now.time()
    if time(9, 30) <= current <= time(11, 30) or time(13, 0) <= current <= time(15, 0):
        return "trading", "交易中", True
    if time(11, 30) < current < time(13, 0):
        return "lunch_break", "午间休市", False
    if current < time(9, 30):
        return "preopen", "盘前", False
    return "closed", "已收盘", False


def market_updated_at() -> datetime | None:
    with connection() as conn:
        value = conn.execute("SELECT MAX(updated_at) FROM market_data WHERE data_source != 'demo'").fetchone()[0]
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=CN_TZ)
    except ValueError:
        return None


@app.get("/api/market")
async def market(force: bool = False):
    now = datetime.now(CN_TZ)
    session, session_label, is_trading = market_session(now)
    updated = market_updated_at()
    refresh_after = 25 if is_trading else 600
    stale = updated is None or (now - updated).total_seconds() >= refresh_after
    refresh_error = None
    if force or stale:
        async with market_refresh_lock:
            updated = market_updated_at()
            stale = updated is None or (datetime.now(CN_TZ) - updated).total_seconds() >= refresh_after
            if force or stale:
                try:
                    await asyncio.to_thread(sync_market)
                except Exception as exc:
                    refresh_error = str(exc)
    with connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM market_data WHERE data_date=(SELECT MAX(data_date) FROM market_data) ORDER BY kind,change_pct DESC")]
    return {
        "date": rows[0]["data_date"] if rows else None,
        "source": rows[0].get("data_source") if rows else None,
        "updated_at": rows[0].get("updated_at") if rows else None,
        "session": session,
        "session_label": session_label,
        "is_trading": is_trading,
        "refresh_interval_seconds": 30 if is_trading else 600,
        "refresh_error": refresh_error,
        "indices": [r for r in rows if r["kind"] == "index"],
        "industries": [r for r in rows if r["kind"] == "industry"],
    }


@app.get("/api/reports/latest")
def latest_report():
    with connection() as conn: row = conn.execute("SELECT * FROM ai_reports ORDER BY report_date DESC LIMIT 1").fetchone()
    return dict(row) if row else None


@app.post("/api/reports/generate")
async def report():
    try: return await generate_report()
    except Exception as exc: raise HTTPException(502, f"AI 日报生成失败：{exc}") from exc
