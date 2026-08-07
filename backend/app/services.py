import json
from datetime import date

import httpx

from .config import settings
from .db import connection
from .real_data import data_status


def holding_rows() -> list[dict]:
    sql = """
    SELECT h.id, f.code, f.name, f.category, f.risk_level, h.shares, h.cost_nav,
           h.target_weight, n.nav, n.daily_change
    FROM holdings h JOIN funds f ON f.code=h.fund_code
    JOIN fund_navs n ON n.fund_code=f.code
    WHERE n.nav_date=(SELECT MAX(nav_date) FROM fund_navs WHERE fund_code=f.code)
    ORDER BY h.id
    """
    with connection() as conn:
        rows = [dict(r) for r in conn.execute(sql)]
    total = sum(r["shares"] * r["nav"] for r in rows) or 1
    for row in rows:
        row["market_value"] = round(row["shares"] * row["nav"], 2)
        row["cost_value"] = round(row["shares"] * row["cost_nav"], 2)
        row["profit"] = round(row["market_value"] - row["cost_value"], 2)
        row["return_pct"] = round((row["nav"] / row["cost_nav"] - 1) * 100, 2)
        row["weight"] = round(row["market_value"] / total * 100, 2)
        row["today_profit"] = round(row["market_value"] * row["daily_change"] / (100 + row["daily_change"]), 2)
    return rows


def dashboard() -> dict:
    rows = holding_rows()
    total = sum(r["market_value"] for r in rows)
    cost = sum(r["cost_value"] for r in rows)
    today_profit = sum(r["today_profit"] for r in rows)
    with connection() as conn:
        report = conn.execute("SELECT * FROM ai_reports ORDER BY report_date DESC LIMIT 1").fetchone()
    suggestion = dict(report)["suggestion"] if report else "组合整体波动可控，维持当前配置，重点观察高波动行业基金。"
    return {"total_assets": round(total, 2), "today_profit": round(today_profit, 2), "total_profit": round(total-cost, 2), "total_return_pct": round((total/cost-1)*100, 2) if cost else 0, "ai_suggestion": suggestion, "holdings": rows[:5], "data_status": data_status()}


def rule_report() -> dict:
    rows = holding_rows()
    strongest = max(rows, key=lambda r: r["daily_change"], default=None)
    weakest = min(rows, key=lambda r: r["daily_change"], default=None)
    concentrated = [r for r in rows if r["weight"] > 35]
    return {
        "market_summary": "市场结构性分化，宽基指数相对平稳，行业主题波动仍然较大。",
        "holding_impact": f"{strongest['name']} 今日贡献相对突出；{weakest['name']} 对组合形成拖累。" if rows else "尚未录入持仓。",
        "suggestion": "保持现有仓位，以观察为主；如连续回撤且基本面未变，可按计划分批调整，避免一次性交易。",
        "risks": "存在单一持仓集中风险。" if concentrated else "当前无明显集中度越线，仍需留意权益市场系统性波动。",
        "watch_conditions": "观察主要指数趋势、行业连续三日强弱变化，以及单只基金仓位是否超过 35%。",
        "source": "rules",
    }


async def generate_report() -> dict:
    base = rule_report()
    if not settings.deepseek_api_key:
        return save_report(base)
    with connection() as conn:
        market = [dict(r) for r in conn.execute("SELECT name,kind,value,change_pct,data_date,data_source FROM market_data WHERE data_date=(SELECT MAX(data_date) FROM market_data)")]
    payload = {"holdings": holding_rows(), "market": market, "data_status": data_status(), "rule_context": base}
    prompt = "你是审慎的个人基金投顾助手。根据JSON数据输出严格JSON，字段为market_summary、holding_impact、suggestion、risks、watch_conditions。不要承诺收益，建议必须包含条件与风险。\n" + json.dumps(payload, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={"model": settings.deepseek_model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}, "temperature": 0.3},
        )
        response.raise_for_status()
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        result["source"] = "deepseek"
        return save_report(result)


def save_report(report: dict) -> dict:
    today = date.today().isoformat()
    keys = ("market_summary", "holding_impact", "suggestion", "risks", "watch_conditions", "source")
    with connection() as conn:
        conn.execute("""INSERT INTO ai_reports(report_date,market_summary,holding_impact,suggestion,risks,watch_conditions,source)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(report_date) DO UPDATE SET market_summary=excluded.market_summary,holding_impact=excluded.holding_impact,suggestion=excluded.suggestion,risks=excluded.risks,watch_conditions=excluded.watch_conditions,source=excluded.source,created_at=CURRENT_TIMESTAMP""", (today, *(report[k] for k in keys)))
        row = conn.execute("SELECT * FROM ai_reports WHERE report_date=?", (today,)).fetchone()
    return dict(row)


