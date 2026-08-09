import os

os.environ["DATABASE_PATH"] = "data/test_fund_assistant.db"
os.environ["AUTO_SYNC_ENABLED"] = "false"
os.environ["DEEPSEEK_API_KEY"] = ""

from fastapi.testclient import TestClient
from app.main import app


def test_core_endpoints():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["total_assets"] > 0
        holdings = client.get("/api/holdings").json()
        assert len(holdings) == 4
        assert "return_pct" in holdings[0]
        fund = client.get(f"/api/funds/{holdings[0]['code']}")
        assert fund.status_code == 200
        assert "target_fund" in fund.json()
        assert "underlying_holdings" in fund.json()
        realtime = client.get("/api/realtime/holdings")
        assert realtime.status_code == 200
        assert realtime.json()["summary"]["total"] == 4
        prediction = client.get(f"/api/predictions/funds/{holdings[0]['code']}")
        assert prediction.status_code == 200
        assert prediction.json()["supported"] is False
        report = client.post("/api/reports/generate")
        assert report.status_code == 200
        assert report.json()["source"] == "rules"
