import json
import re
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from .db import connection


SOURCE = "东方财富 / 天天基金"
MARKET_SOURCE = "新浪财经 / 申万宏源"
CN_TZ = ZoneInfo("Asia/Shanghai")
SYNC_LOCK = threading.Lock()


def now_text() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=30,
        trust_env=False,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"},
    )


def _quote_json(client: httpx.Client, path: str, params: dict) -> dict:
    last_error = None
    for host in ("push2.eastmoney.com", "17.push2.eastmoney.com", "33.push2.eastmoney.com", "82.push2.eastmoney.com"):
        try:
            response = client.get(f"https://{host}{path}", params=params, headers={"Referer": "https://quote.eastmoney.com/"})
            response.raise_for_status()
            payload = response.json()
            if payload.get("data"):
                return payload
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"东方财富行情节点暂不可用：{last_error}")


def _json_var(script: str, name: str, default=None):
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*(.*?);", script, re.S)
    if not match:
        return default
    try:
        return json.loads(match.group(1).lstrip("\ufeff"))
    except json.JSONDecodeError:
        return default


def _string_var(script: str, name: str, default="") -> str:
    value = _json_var(script, name, default)
    return value if isinstance(value, str) else default


def search_funds(query: str, limit: int = 10) -> list[dict]:
    if not query.strip():
        return []
    with _client() as client:
        response = client.get(
            "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx",
            params={"m": 1, "key": query.strip()},
        )
        response.raise_for_status()
        items = response.json().get("Datas", [])
    results = []
    for item in items:
        base = item.get("FundBaseInfo") or {}
        if item.get("CATEGORYDESC") != "基金" or not item.get("CODE"):
            continue
        results.append({
            "code": item["CODE"],
            "name": base.get("SHORTNAME") or item.get("NAME") or "未知基金",
            "category": base.get("FTYPE") or "基金",
            "manager": base.get("JJJL") or "",
            "company": base.get("JJGS") or "",
            "latest_nav": base.get("DWJZ"),
            "nav_date": base.get("FSRQ"),
            "purchasable": base.get("ISBUY") == "1",
        })
        if len(results) >= limit:
            break
    return results


def _fund_positions(client: httpx.Client, code: str) -> tuple[str, list[dict]]:
    current_year = datetime.now(CN_TZ).year
    for year in (current_year, current_year - 1):
        response = client.get(
            "https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
            params={"type": "jjcc", "code": code, "topline": 10, "year": year},
            headers={"Referer": f"https://fundf10.eastmoney.com/ccmx_{code}.html"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.select_one("h4.t")
        date_match = re.search(r"截止至：\s*(\d{4}-\d{2}-\d{2})", title.get_text(" ", strip=True) if title else "")
        rows = []
        for tr in soup.select("table tbody tr")[:10]:
            cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]
            if len(cells) < 9:
                continue
            try:
                rows.append({
                    "stock_code": cells[1], "stock_name": cells[2],
                    "weight": float(cells[6].replace("%", "") or 0),
                    "shares_10k": float(cells[7].replace(",", "") or 0),
                    "market_value_10k": float(cells[8].replace(",", "") or 0),
                })
            except ValueError:
                continue
        if rows:
            return (date_match.group(1) if date_match else str(year), rows)
    return "", []


def _latest_expected_position_date() -> str:
    today = datetime.now(CN_TZ).date()
    marker = (today.month, today.day)
    if marker >= (7, 21):
        return f"{today.year}-06-30"
    if marker >= (4, 22):
        return f"{today.year}-03-31"
    if marker >= (1, 23):
        return f"{today.year - 1}-12-31"
    return f"{today.year - 1}-09-30"


def sync_fund(code: str) -> dict:
    code = code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("基金代码必须是 6 位数字")
    started = now_text()
    try:
        with connection() as conn:
            mapping_row = conn.execute("SELECT * FROM fund_realtime_mappings WHERE fund_code=?", (code,)).fetchone()
            mapping = dict(mapping_row) if mapping_row else None
        with _client() as client:
            search = search_funds(code, 20)
            meta = next((item for item in search if item["code"] == code), None)
            if not meta:
                raise ValueError("未找到该基金代码")
            response = client.get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js", params={"v": int(datetime.now().timestamp())})
            response.raise_for_status()
            script = response.text
            navs = _json_var(script, "Data_netWorthTrend", []) or []
            managers = _json_var(script, "Data_currentFundManager", []) or []
            manager = ", ".join(m.get("name", "") for m in managers if m.get("name")) or meta["manager"]
            position_date, positions = _fund_positions(client, code)
            target_position_date, target_positions = ("", [])
            if mapping:
                target_position_date, target_positions = _fund_positions(client, mapping["target_etf_code"])
        if mapping and position_date and position_date < _latest_expected_position_date():
            positions = []
            position_date = ""
        if not navs:
            raise ValueError("行情源未返回净值历史")
        updated = now_text()
        latest_date = datetime.fromtimestamp(navs[-1]["x"] / 1000, CN_TZ).date().isoformat()
        with connection() as conn:
            conn.execute(
                """INSERT INTO funds(code,name,category,risk_level,manager,benchmark,company,data_source,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,category=excluded.category,
                manager=excluded.manager,company=excluded.company,data_source=excluded.data_source,updated_at=excluded.updated_at""",
                (code, meta["name"], meta["category"], "以基金合同为准", manager, "以基金合同为准", meta["company"], SOURCE, updated),
            )
            conn.execute("DELETE FROM fund_navs WHERE fund_code=? AND data_source='demo'", (code,))
            for item in navs[-1200:]:
                nav_date = datetime.fromtimestamp(item["x"] / 1000, CN_TZ).date().isoformat()
                conn.execute(
                    """INSERT INTO fund_navs(fund_code,nav_date,nav,daily_change,data_source,updated_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(fund_code,nav_date) DO UPDATE SET nav=excluded.nav,
                    daily_change=excluded.daily_change,data_source=excluded.data_source,updated_at=excluded.updated_at""",
                    (code, nav_date, float(item["y"]), float(item.get("equityReturn") or 0), SOURCE, updated),
                )
            if mapping:
                conn.execute("DELETE FROM fund_positions WHERE fund_code=?", (code,))
            if positions:
                conn.execute("DELETE FROM fund_positions WHERE fund_code=?", (code,))
                conn.executemany(
                    "INSERT INTO fund_positions(fund_code,report_date,stock_code,stock_name,weight,shares_10k,market_value_10k,data_source,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    [(code, position_date, p["stock_code"], p["stock_name"], p["weight"], p["shares_10k"], p["market_value_10k"], SOURCE, updated) for p in positions],
                )
            if mapping and target_positions:
                conn.execute(
                    "INSERT OR IGNORE INTO funds(code,name,category,risk_level,data_source,updated_at) VALUES(?,?,?,?,?,?)",
                    (mapping["target_etf_code"], mapping["target_etf_name"], "ETF", "以基金合同为准", SOURCE, updated),
                )
                conn.execute("DELETE FROM fund_positions WHERE fund_code=?", (mapping["target_etf_code"],))
                conn.executemany(
                    "INSERT INTO fund_positions(fund_code,report_date,stock_code,stock_name,weight,shares_10k,market_value_10k,data_source,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    [(mapping["target_etf_code"], target_position_date, p["stock_code"], p["stock_name"], p["weight"], p["shares_10k"], p["market_value_10k"], SOURCE, updated) for p in target_positions],
                )
            conn.execute("INSERT INTO sync_runs(scope,status,data_date,source,records,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?)", (f"fund:{code}", "success", latest_date, SOURCE, len(navs[-1200:]), None, started, updated))
        return {"scope": f"fund:{code}", "status": "success", "data_date": latest_date, "records": len(navs[-1200:]), "positions": len(positions), "target_positions": len(target_positions), "target_position_date": target_position_date or None, "source": SOURCE}
    except Exception as exc:
        finished = now_text()
        with connection() as conn:
            conn.execute("INSERT INTO sync_runs(scope,status,source,records,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?)", (f"fund:{code}", "failed", SOURCE, 0, str(exc)[:500], started, finished))
        raise


def sync_market() -> dict:
    started = now_text()
    try:
        with _client() as client:
            index_response = client.get(
                "https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006,s_sh000300",
                headers={"Referer": "https://finance.sina.com.cn/"},
            )
            index_response.raise_for_status()
            index_response.encoding = "gb18030"
            indices = []
            for line in index_response.text.splitlines():
                match = re.search(r'hq_str_s_[^=]+="([^"]+)"', line)
                if not match:
                    continue
                fields = match.group(1).split(",")
                if len(fields) >= 4:
                    indices.append({"name": fields[0], "value": float(fields[1]), "change": float(fields[3])})
        import akshare as ak
        industry_frame = ak.index_realtime_sw(symbol="一级行业")
        industries = []
        for row in industry_frame.to_dict("records"):
            previous, latest = float(row["昨收盘"]), float(row["最新价"])
            if previous:
                industries.append({"name": row["指数名称"], "value": latest, "change": round((latest / previous - 1) * 100, 2)})
        industries.sort(key=lambda item: item["change"], reverse=True)
        selected = industries[:6] + industries[-6:]
        data_date, updated = datetime.now(CN_TZ).date().isoformat(), now_text()
        with connection() as conn:
            conn.execute("DELETE FROM market_data WHERE data_date=?", (data_date,))
            for item in indices:
                conn.execute("INSERT INTO market_data(data_date,name,kind,value,change_pct,data_source,updated_at) VALUES(?,?,?,?,?,?,?)", (data_date, item["name"], "index", item["value"], item["change"], MARKET_SOURCE, updated))
            for item in selected:
                conn.execute("INSERT INTO market_data(data_date,name,kind,value,change_pct,data_source,updated_at) VALUES(?,?,?,?,?,?,?)", (data_date, item["name"], "industry", item["value"], item["change"], MARKET_SOURCE, updated))
            count = len(indices) + len(selected)
            conn.execute("INSERT INTO sync_runs(scope,status,data_date,source,records,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?)", ("market", "success", data_date, MARKET_SOURCE, count, None, started, updated))
        return {"scope": "market", "status": "success", "data_date": data_date, "records": count, "source": MARKET_SOURCE}
    except Exception as exc:
        finished = now_text()
        with connection() as conn:
            conn.execute("INSERT INTO sync_runs(scope,status,source,records,error,started_at,finished_at) VALUES(?,?,?,?,?,?,?)", ("market", "failed", MARKET_SOURCE, 0, str(exc)[:500], started, finished))
        raise


def sync_all() -> dict:
    with SYNC_LOCK:
        try:
            with connection() as conn:
                codes = [row[0] for row in conn.execute("SELECT DISTINCT fund_code FROM holdings ORDER BY fund_code")]
            results, errors = [], []
            for code in codes:
                try:
                    results.append(sync_fund(code))
                except Exception as exc:
                    errors.append({"scope": f"fund:{code}", "error": str(exc)})
            try:
                results.append(sync_market())
            except Exception as exc:
                errors.append({"scope": "market", "error": str(exc)})
            return {"status": "partial" if errors else "success", "results": results, "errors": errors, "finished_at": now_text()}
        except Exception:
            raise


def data_status() -> dict:
    with connection() as conn:
        nav = conn.execute("SELECT MAX(nav_date), MAX(updated_at) FROM fund_navs WHERE data_source != 'demo'").fetchone()
        market = conn.execute("SELECT MAX(data_date), MAX(updated_at) FROM market_data WHERE data_source != 'demo'").fetchone()
        latest = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        real_funds = conn.execute("SELECT COUNT(DISTINCT fund_code) FROM fund_navs WHERE data_source != 'demo'").fetchone()[0]
        total_funds = conn.execute("SELECT COUNT(DISTINCT fund_code) FROM holdings").fetchone()[0]
    return {
        "mode": "real" if real_funds == total_funds and total_funds > 0 and market[0] else "mixed" if real_funds or market[0] else "demo",
        "funds": {"real": real_funds, "total": total_funds, "data_date": nav[0], "updated_at": nav[1]},
        "market": {"data_date": market[0], "updated_at": market[1]},
        "latest_sync": dict(latest) if latest else None,
        "source": SOURCE,
    }


def _sina_etf_quote(code: str) -> dict:
    market = "sh" if code.startswith(("5", "6")) else "sz"
    with _client() as client:
        response = client.get(
            f"https://hq.sinajs.cn/list={market}{code}",
            headers={"Referer": "https://finance.sina.com.cn/"},
        )
        response.raise_for_status()
        response.encoding = "gb18030"
    match = re.search(r'="([^"]+)"', response.text)
    fields = match.group(1).split(",") if match else []
    if len(fields) < 32 or not fields[2] or not fields[3]:
        raise ValueError("目标 ETF 暂无实时行情")
    previous, current = float(fields[2]), float(fields[3])
    return {
        "name": fields[0], "value": current,
        "change_pct": (current / previous - 1) * 100 if previous else 0,
        "quote_time": f"{fields[30]}T{fields[31]}+08:00",
        "quote_source": "新浪财经目标 ETF 行情", "method": "target_etf",
    }


def realtime_estimate(fund_code: str, shares: float, cost_nav: float) -> dict:
    with connection() as conn:
        mapping = conn.execute("SELECT * FROM fund_realtime_mappings WHERE fund_code=?", (fund_code,)).fetchone()
        nav = conn.execute(
            "SELECT nav,nav_date FROM fund_navs WHERE fund_code=? AND data_source!='demo' ORDER BY nav_date DESC LIMIT 1",
            (fund_code,),
        ).fetchone()
    if not mapping or not nav:
        return {"supported": False, "fund_code": fund_code, "reason": "该基金尚未配置盘中估值映射"}
    mapping, nav = dict(mapping), dict(nav)
    quote = None
    if mapping.get("target_index_code"):
        try:
            with _client() as quote_client:
                payload = _quote_json(
                    quote_client, "/api/qt/stock/get",
                    {"secid": f"2.{mapping['target_index_code']}", "fltt": 2, "fields": "f43,f57,f58,f60,f86,f169,f170"},
                ).get("data", {})
            quote_time = datetime.fromtimestamp(payload["f86"], CN_TZ).isoformat(timespec="seconds") if payload.get("f86") else now_text()
            quote = {"name": payload["f58"], "value": float(payload["f43"]), "change_pct": float(payload["f170"]), "quote_time": quote_time, "quote_source": "东方财富中证指数行情", "method": "target_index"}
        except Exception:
            quote = None
    if quote is None:
        quote = _sina_etf_quote(mapping["target_etf_code"])
    quote_date = quote["quote_time"][:10]
    effective_change = 0.0 if quote_date <= nav["nav_date"] else quote["change_pct"] * float(mapping["exposure_ratio"])
    estimated_nav = float(nav["nav"]) * (1 + effective_change / 100)
    official_value = float(nav["nav"]) * shares
    estimated_value = estimated_nav * shares
    return {
        "supported": True, "fund_code": fund_code,
        "official_nav": float(nav["nav"]), "official_nav_date": nav["nav_date"],
        "estimated_nav": round(estimated_nav, 4), "estimated_change_pct": round(effective_change, 2),
        "estimated_today_profit": round(estimated_value - official_value, 2),
        "estimated_market_value": round(estimated_value, 2),
        "estimated_total_profit": round(estimated_value - shares * cost_nav, 2),
        "estimated_total_return_pct": round((estimated_nav / cost_nav - 1) * 100, 2) if cost_nav else 0,
        "target_etf_code": mapping["target_etf_code"], "target_etf_name": mapping["target_etf_name"],
        "target_index_code": mapping["target_index_code"], "target_index_name": mapping["target_index_name"],
        "target_change_pct": round(quote["change_pct"], 2), "exposure_ratio": mapping["exposure_ratio"],
        "quote_time": quote["quote_time"], "quote_source": quote["quote_source"], "method": quote["method"],
        "disclaimer": "盘中估值基于目标指数或 ETF 行情推算，不等于基金公司最终净值。",
    }


def realtime_holdings() -> dict:
    with connection() as conn:
        rows = [dict(row) for row in conn.execute("SELECT id,fund_code,shares,cost_nav FROM holdings ORDER BY id")]
    estimates = [realtime_estimate(row["fund_code"], row["shares"], row["cost_nav"]) | {"holding_id": row["id"]} for row in rows]
    supported = [item for item in estimates if item["supported"]]
    return {
        "items": estimates,
        "summary": {
            "estimated_market_value": round(sum(item["estimated_market_value"] for item in supported), 2),
            "estimated_today_profit": round(sum(item["estimated_today_profit"] for item in supported), 2),
            "estimated_total_profit": round(sum(item["estimated_total_profit"] for item in supported), 2),
            "supported": len(supported), "total": len(estimates),
            "quote_time": max((item["quote_time"] for item in supported), default=None),
        },
    }
