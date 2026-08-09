import numpy as np
import pandas as pd

from app import prediction


def synthetic_history(rows: int = 760) -> pd.DataFrame:
    random = np.random.default_rng(42)
    returns = random.normal(0.0004, 0.018, rows)
    close = 1.2 * np.cumprod(1 + returns)
    open_price = close * (1 + random.normal(0, 0.004, rows))
    high = np.maximum(open_price, close) * (1 + random.uniform(0.001, 0.015, rows))
    low = np.minimum(open_price, close) * (1 - random.uniform(0.001, 0.015, rows))
    return pd.DataFrame({
        "date": pd.bdate_range("2023-01-02", periods=rows),
        "open": open_price, "close": close, "high": high, "low": low,
        "volume": random.integers(1_000_000, 8_000_000, rows),
        "amount": random.integers(50_000_000, 500_000_000, rows),
        "turnover": random.uniform(0.5, 8, rows),
    })


def test_feature_frame_uses_next_day_label_without_losing_latest_row():
    labelled, latest = prediction.build_feature_frame(synthetic_history())
    assert len(labelled) >= 690
    assert len(latest) == 1
    assert latest.iloc[0]["date"] > labelled.iloc[-1]["date"]
    assert set(prediction.FEATURE_NAMES).issubset(labelled.columns)


def test_failed_backtest_forces_research_only_signal(monkeypatch):
    weak_validation = {
        "accuracy": 0.51, "baseline_accuracy": 0.53, "auc": 0.50, "brier": 0.26,
        "validation_samples": 300, "training_samples": 699, "method": "测试滚动验证",
    }
    monkeypatch.setattr(prediction, "walk_forward_validate", lambda _: weak_validation)
    result = prediction.train_prediction(
        "007818",
        {"target_etf_code": "515880", "target_etf_name": "通信ETF", "exposure_ratio": 0.91},
        synthetic_history(),
    )
    assert result["qualified"] is False
    assert result["signal"] == "方向不明"
    assert result["confidence"] == "低"
    assert 0 <= result["up_probability"] <= 1
