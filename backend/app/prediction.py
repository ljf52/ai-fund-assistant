import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import akshare as ak
import httpx
import numpy as np
import pandas as pd
import xgboost as xgb

from .db import connection


CN_TZ = ZoneInfo("Asia/Shanghai")
MODEL_NAME = "xgboost-direction-v1"
PREDICTION_LOCK = threading.Lock()
FEATURE_NAMES = [
    "return_1d", "return_3d", "return_5d", "return_10d", "return_20d",
    "ma_gap_5d", "ma_gap_10d", "ma_gap_20d", "ma_gap_60d",
    "volatility_5d", "volatility_20d", "volume_ratio_5d", "volume_ratio_20d",
    "amount_ratio_20d", "intraday_range", "close_position", "turnover",
]
FEATURE_LABELS = {
    "return_1d": "近1日动量", "return_3d": "近3日动量", "return_5d": "近5日动量",
    "return_10d": "近10日动量", "return_20d": "近20日动量",
    "ma_gap_5d": "5日均线距离", "ma_gap_10d": "10日均线距离",
    "ma_gap_20d": "20日均线距离", "ma_gap_60d": "60日趋势距离",
    "volatility_5d": "短期波动率", "volatility_20d": "20日波动率",
    "volume_ratio_5d": "5日量能变化", "volume_ratio_20d": "20日量能变化",
    "amount_ratio_20d": "成交额变化", "intraday_range": "日内振幅",
    "close_position": "收盘位置", "turnover": "换手率",
}


def _cached_prediction(fund_code: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """SELECT payload_json FROM prediction_runs
            WHERE fund_code=? AND created_at>=datetime('now','-12 hours')
            ORDER BY created_at DESC LIMIT 1""",
            (fund_code,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def _latest_prediction(fund_code: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM prediction_runs WHERE fund_code=? ORDER BY created_at DESC LIMIT 1",
            (fund_code,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def _mapping(fund_code: str) -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM fund_realtime_mappings WHERE fund_code=?", (fund_code,)).fetchone()
    return dict(row) if row else None


def fetch_target_history(target_code: str) -> pd.DataFrame:
    end = datetime.now(CN_TZ).strftime("%Y%m%d")
    market = "1" if target_code.startswith(("5", "6")) else "0"
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989", "klt": "101", "fqt": "1",
        "beg": "20180101", "end": end, "secid": f"{market}.{target_code}",
    }
    frame = pd.DataFrame()
    last_error = None
    for host in ("push2his.eastmoney.com", "33.push2his.eastmoney.com", "82.push2his.eastmoney.com"):
        try:
            with httpx.Client(timeout=30, trust_env=False, headers={"Referer": "https://quote.eastmoney.com/"}) as client:
                response = client.get(f"https://{host}/api/qt/stock/kline/get", params=params)
                response.raise_for_status()
                lines = (response.json().get("data") or {}).get("klines") or []
            if lines:
                frame = pd.DataFrame(
                    [line.split(",")[:11] for line in lines],
                    columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"],
                )
                break
        except Exception as exc:
            last_error = exc
    if frame.empty:
        try:
            frame = ak.fund_etf_hist_em(
                symbol=target_code, period="daily", start_date="20180101", end_date=end, adjust="qfq"
            )
        except Exception as exc:
            raise RuntimeError(f"目标 ETF 历史行情暂不可用：{last_error or exc}") from exc
    if frame.empty:
        raise ValueError("目标 ETF 历史行情为空")
    columns = {
        "日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "amount", "换手率": "turnover",
    }
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise ValueError(f"目标 ETF 历史行情缺少字段：{', '.join(missing)}")
    frame = frame.rename(columns=columns)[list(columns.values())].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    for column in columns.values():
        if column != "date":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna().drop_duplicates("date").sort_values("date").reset_index(drop=True)


def fund_nav_history(fund_code: str) -> pd.DataFrame:
    with connection() as conn:
        rows = conn.execute(
            """SELECT nav_date,nav FROM fund_navs
            WHERE fund_code=? AND data_source!='demo' ORDER BY nav_date""",
            (fund_code,),
        ).fetchall()
    if len(rows) < 520:
        raise ValueError("基金真实净值历史不足 520 个交易日")
    close = pd.Series([float(row["nav"]) for row in rows], dtype=float)
    previous = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame({
        "date": pd.to_datetime([row["nav_date"] for row in rows]),
        "open": previous, "close": close,
        "high": np.maximum(previous, close), "low": np.minimum(previous, close),
        "volume": np.ones(len(rows)), "amount": np.ones(len(rows)), "turnover": np.zeros(len(rows)),
    })


def build_feature_frame(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = history.copy()
    daily_return = data["close"].pct_change()
    for days in (1, 3, 5, 10, 20):
        data[f"return_{days}d"] = data["close"].pct_change(days)
    for days in (5, 10, 20, 60):
        data[f"ma_gap_{days}d"] = data["close"] / data["close"].rolling(days).mean() - 1
    data["volatility_5d"] = daily_return.rolling(5).std()
    data["volatility_20d"] = daily_return.rolling(20).std()
    data["volume_ratio_5d"] = data["volume"] / data["volume"].rolling(5).mean() - 1
    data["volume_ratio_20d"] = data["volume"] / data["volume"].rolling(20).mean() - 1
    data["amount_ratio_20d"] = data["amount"] / data["amount"].rolling(20).mean() - 1
    previous_close = data["close"].shift(1)
    data["intraday_range"] = (data["high"] - data["low"]) / previous_close
    spread = (data["high"] - data["low"]).replace(0, np.nan)
    data["close_position"] = (data["close"] - data["low"]) / spread
    data["turnover"] = data["turnover"] / 100
    data["next_return"] = data["close"].shift(-1) / data["close"] - 1
    latest = data.dropna(subset=FEATURE_NAMES).tail(1)
    labelled = data.dropna(subset=FEATURE_NAMES + ["next_return"]).copy()
    labelled["label"] = (labelled["next_return"] > 0).astype(int)
    return labelled, latest


def _auc_score(labels: np.ndarray, probabilities: np.ndarray) -> float:
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if not positives or not negatives:
        return 0.5
    ranks = pd.Series(probabilities).rank(method="average").to_numpy()
    return float((ranks[labels == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def _train_model(features: np.ndarray, labels: np.ndarray) -> xgb.Booster:
    matrix = xgb.DMatrix(features, label=labels, feature_names=FEATURE_NAMES)
    params = {
        "objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 3,
        "eta": 0.04, "min_child_weight": 8, "subsample": 0.85,
        "colsample_bytree": 0.8, "lambda": 2.0, "seed": 42, "nthread": 2,
    }
    return xgb.train(params, matrix, num_boost_round=140, verbose_eval=False)


def walk_forward_validate(labelled: pd.DataFrame) -> dict:
    features = labelled[FEATURE_NAMES].to_numpy(dtype=float)
    labels = labelled["label"].to_numpy(dtype=int)
    sample_count = len(labelled)
    initial_train = max(400, int(sample_count * 0.55))
    if sample_count - initial_train < 120:
        raise ValueError("有效历史样本不足，至少需要约 520 个交易日")
    boundaries = np.linspace(initial_train, sample_count, 5, dtype=int)
    all_labels, all_probabilities, all_baselines = [], [], []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        model = _train_model(features[:start], labels[:start])
        probabilities = model.predict(xgb.DMatrix(features[start:end], feature_names=FEATURE_NAMES))
        majority = int(labels[:start].mean() >= 0.5)
        all_labels.extend(labels[start:end])
        all_probabilities.extend(probabilities)
        all_baselines.extend([majority] * (end - start))
    observed = np.asarray(all_labels, dtype=int)
    predicted = np.asarray(all_probabilities, dtype=float)
    decisions = (predicted >= 0.5).astype(int)
    return {
        "accuracy": round(float((decisions == observed).mean()), 4),
        "baseline_accuracy": round(float((np.asarray(all_baselines) == observed).mean()), 4),
        "auc": round(_auc_score(observed, predicted), 4),
        "brier": round(float(np.mean((predicted - observed) ** 2)), 4),
        "validation_samples": len(observed), "training_samples": sample_count,
        "method": "扩展窗口滚动验证（4折）",
    }


def _format_feature_value(name: str, value: float) -> str:
    if name == "close_position":
        return f"日内 {value * 100:.0f}% 位置"
    return f"{value * 100:+.2f}%"


def train_prediction(
    fund_code: str, mapping: dict, history: pd.DataFrame,
    training_basis: str = "target_etf", source_warning: str | None = None,
) -> dict:
    labelled, latest = build_feature_frame(history)
    if latest.empty:
        raise ValueError("历史行情不足以生成特征")
    validation = walk_forward_validate(labelled)
    features = labelled[FEATURE_NAMES].to_numpy(dtype=float)
    labels = labelled["label"].to_numpy(dtype=int)
    model = _train_model(features, labels)
    latest_values = latest[FEATURE_NAMES].to_numpy(dtype=float)
    matrix = xgb.DMatrix(latest_values, feature_names=FEATURE_NAMES)
    probability = float(model.predict(matrix)[0])
    contributions = model.predict(matrix, pred_contribs=True)[0][:-1]
    factor_indexes = np.argsort(np.abs(contributions))[::-1][:4]
    factors = [
        {
            "name": FEATURE_LABELS[FEATURE_NAMES[index]],
            "direction": "positive" if contributions[index] >= 0 else "negative",
            "value": _format_feature_value(FEATURE_NAMES[index], float(latest_values[0, index])),
        }
        for index in factor_indexes
    ]
    recent_returns = labelled["next_return"].tail(500)
    positive_mean = float(recent_returns[recent_returns > 0].mean())
    negative_mean = float(recent_returns[recent_returns <= 0].mean())
    expected_etf_return = probability * positive_mean + (1 - probability) * negative_mean
    interval_returns = labelled["next_return"].tail(252)
    exposure = float(mapping["exposure_ratio"]) if training_basis == "target_etf" else 1.0
    expected_return = expected_etf_return * exposure * 100
    lower_bound = float(interval_returns.quantile(0.10)) * exposure * 100
    upper_bound = float(interval_returns.quantile(0.90)) * exposure * 100
    edge = abs(probability - 0.5)
    qualified = validation["auc"] >= 0.52 and validation["accuracy"] > validation["baseline_accuracy"]
    if not qualified:
        confidence = "低"
        signal = "方向不明"
        status_message = "滚动回测尚未超过简单基准，本次概率仅供模型研究。"
    elif validation["auc"] >= 0.58 and edge >= 0.15:
        confidence = "较高"
        signal = "偏强" if probability >= 0.58 else "偏弱" if probability <= 0.42 else "方向不明"
        status_message = "模型通过当前历史基准，仍需结合风险承受能力持续观察。"
    else:
        confidence = "中等"
        signal = "偏强" if probability >= 0.58 else "偏弱" if probability <= 0.42 else "方向不明"
        status_message = "模型略高于当前历史基准，信号强度有限。"
    as_of_date = latest.iloc[0]["date"].date().isoformat()
    return {
        "supported": True, "fund_code": fund_code,
        "target_code": mapping["target_etf_code"], "target_name": mapping["target_etf_name"],
        "horizon": "下一交易日", "as_of_date": as_of_date,
        "up_probability": round(probability, 4), "down_probability": round(1 - probability, 4),
        "expected_return_pct": round(expected_return, 2),
        "lower_bound_pct": round(lower_bound, 2), "upper_bound_pct": round(upper_bound, 2),
        "signal": signal, "confidence": confidence, "qualified": qualified,
        "status_message": status_message, "exposure_ratio": float(mapping["exposure_ratio"]),
        "factors": factors, "validation": validation, "model_name": MODEL_NAME,
        "training_basis": training_basis,
        "data_source": "东方财富目标 ETF 前复权日线" if training_basis == "target_etf" else "天天基金官方净值历史（ETF 行情回退）",
        "source_warning": source_warning,
        "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "disclaimer": "概率来自历史行情模型，不保证未来结果；区间为近期历史分布估计，不是收益承诺。",
    }


def get_prediction(fund_code: str, force: bool = False) -> dict:
    fund_code = fund_code.strip()
    if not force:
        cached = _cached_prediction(fund_code)
        if cached:
            return cached
    mapping = _mapping(fund_code)
    if not mapping:
        return {"supported": False, "fund_code": fund_code, "reason": "该基金尚未配置预测标的映射"}
    with PREDICTION_LOCK:
        if not force:
            cached = _cached_prediction(fund_code)
            if cached:
                return cached
        source_warning = None
        try:
            history = fetch_target_history(mapping["target_etf_code"])
            training_basis = "target_etf"
        except Exception as target_error:
            try:
                history = fund_nav_history(fund_code)
                training_basis = "fund_nav"
                source_warning = f"目标 ETF 历史行情暂不可用，已回退基金官方净值：{target_error}"
            except Exception:
                stale = _latest_prediction(fund_code)
                if stale:
                    stale["stale"] = True
                    stale["source_warning"] = f"历史行情刷新失败，当前显示最近一次模型结果：{target_error}"
                    return stale
                raise
        result = train_prediction(fund_code, mapping, history, training_basis, source_warning)
        payload = json.dumps(result, ensure_ascii=False)
        with connection() as conn:
            conn.execute(
                """INSERT INTO prediction_runs(fund_code,target_code,as_of_date,horizon_days,model_name,payload_json,created_at)
                VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(fund_code,target_code,as_of_date,horizon_days) DO UPDATE SET
                model_name=excluded.model_name,payload_json=excluded.payload_json,created_at=CURRENT_TIMESTAMP""",
                (fund_code, mapping["target_etf_code"], result["as_of_date"], 1, MODEL_NAME, payload),
            )
        return result
