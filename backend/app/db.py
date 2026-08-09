import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS funds (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
  risk_level TEXT NOT NULL, manager TEXT DEFAULT '', benchmark TEXT DEFAULT '',
  company TEXT DEFAULT '', data_source TEXT DEFAULT 'demo', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS holdings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1,
  fund_code TEXT NOT NULL, shares REAL NOT NULL, cost_nav REAL NOT NULL,
  target_weight REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(fund_code) REFERENCES funds(code)
);
CREATE TABLE IF NOT EXISTS fund_navs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, fund_code TEXT NOT NULL, nav_date TEXT NOT NULL,
  nav REAL NOT NULL, daily_change REAL NOT NULL DEFAULT 0,
  data_source TEXT DEFAULT 'demo', updated_at TEXT,
  UNIQUE(fund_code, nav_date), FOREIGN KEY(fund_code) REFERENCES funds(code)
);
CREATE TABLE IF NOT EXISTS market_data (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_date TEXT NOT NULL, name TEXT NOT NULL,
  kind TEXT NOT NULL, value REAL NOT NULL, change_pct REAL NOT NULL,
  data_source TEXT DEFAULT 'demo', updated_at TEXT,
  UNIQUE(data_date, name, kind)
);
CREATE TABLE IF NOT EXISTS ai_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, report_date TEXT NOT NULL UNIQUE,
  market_summary TEXT NOT NULL, holding_impact TEXT NOT NULL,
  suggestion TEXT NOT NULL, risks TEXT NOT NULL, watch_conditions TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'rules', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fund_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, fund_code TEXT NOT NULL, report_date TEXT NOT NULL,
  stock_code TEXT NOT NULL, stock_name TEXT NOT NULL, weight REAL NOT NULL,
  shares_10k REAL DEFAULT 0, market_value_10k REAL DEFAULT 0,
  data_source TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(fund_code, report_date, stock_code), FOREIGN KEY(fund_code) REFERENCES funds(code)
);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, status TEXT NOT NULL,
  data_date TEXT, source TEXT NOT NULL, records INTEGER DEFAULT 0, error TEXT,
  started_at TEXT NOT NULL, finished_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fund_realtime_mappings (
  fund_code TEXT PRIMARY KEY, target_etf_code TEXT NOT NULL, target_etf_name TEXT NOT NULL,
  target_index_code TEXT, target_index_name TEXT, exposure_ratio REAL NOT NULL DEFAULT 0.90,
  source TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(fund_code) REFERENCES funds(code)
);
CREATE TABLE IF NOT EXISTS prediction_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, fund_code TEXT NOT NULL,
  target_code TEXT NOT NULL, as_of_date TEXT NOT NULL, horizon_days INTEGER NOT NULL DEFAULT 1,
  model_name TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(fund_code, target_code, as_of_date, horizon_days)
);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    additions = {
        "funds": {"company": "TEXT DEFAULT ''", "data_source": "TEXT DEFAULT 'demo'", "updated_at": "TEXT"},
        "fund_navs": {"data_source": "TEXT DEFAULT 'demo'", "updated_at": "TEXT"},
        "market_data": {"data_source": "TEXT DEFAULT 'demo'", "updated_at": "TEXT"},
    }
    for table, columns in additions.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.database_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
        conn.execute(
            """INSERT OR IGNORE INTO fund_realtime_mappings
            (fund_code,target_etf_code,target_etf_name,target_index_code,target_index_name,exposure_ratio,source,updated_at)
            SELECT '007818','515880','通信ETF','931160','中证全指通信设备指数',0.91,'基金合同 / 中证指数','2026-08-07'
            WHERE EXISTS(SELECT 1 FROM funds WHERE code='007818')"""
        )
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        conn.execute("INSERT INTO users(id, name) VALUES(1, ?)", ("默认用户",))
        funds = [
            ("000001", "华夏成长混合", "混合型", "中高风险", "示例经理", "沪深300"),
            ("110022", "易方达消费行业", "股票型", "高风险", "示例经理", "中证消费"),
            ("161725", "招商中证白酒指数", "指数型", "高风险", "示例经理", "中证白酒"),
            ("005827", "易方达蓝筹精选", "混合型", "中高风险", "示例经理", "沪深300"),
        ]
        conn.executemany("INSERT INTO funds(code,name,category,risk_level,manager,benchmark) VALUES(?,?,?,?,?,?)", funds)
        holdings = [(1, "000001", 12500, 1.318, 25), (1, "110022", 6800, 3.02, 30), (1, "161725", 9000, 1.08, 20), (1, "005827", 7200, 1.94, 25)]
        conn.executemany("INSERT INTO holdings(user_id,fund_code,shares,cost_nav,target_weight) VALUES(?,?,?,?,?)", holdings)
        today = date.today()
        bases = {"000001": 1.42, "110022": 2.86, "161725": 1.17, "005827": 1.82}
        for code, base in bases.items():
            previous = base * 0.86
            for days_ago in range(89, -1, -1):
                d = today - timedelta(days=days_ago)
                trend = (89 - days_ago) / 89 * base * 0.14
                wave = (((days_ago * 17 + int(code[-2:])) % 19) - 9) / 900
                nav = round(base * 0.86 + trend + wave, 4)
                change = round((nav / previous - 1) * 100, 2)
                conn.execute("INSERT INTO fund_navs(fund_code,nav_date,nav,daily_change) VALUES(?,?,?,?)", (code, d.isoformat(), nav, change))
                previous = nav
        markets = [("沪深300", "index", 4128.56, 0.72), ("上证指数", "index", 3654.12, 0.44), ("创业板指", "index", 2388.63, -0.31), ("人工智能", "industry", 0, 2.41), ("医药生物", "industry", 0, 1.18), ("食品饮料", "industry", 0, -0.76), ("新能源", "industry", 0, -1.32)]
        conn.executemany("INSERT INTO market_data(data_date,name,kind,value,change_pct) VALUES(?,?,?,?,?)", [(today.isoformat(), *m) for m in markets])
