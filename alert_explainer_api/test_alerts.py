from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def _alert_payload() -> dict[str, str | float]:
    return {
        "title": "CPU usage high",
        "severity": "critical",
        "source": "api-gateway",
        "metric_name": "cpu_utilization",
        "metric_value": 95.0,
        "threshold": 80.0,
    }


def test_create_alert(client: TestClient):
    response = client.post("/alerts/", json=_alert_payload())

    assert response.status_code == 201
    alert = response.json()
    assert alert["id"] > 0
    assert alert["title"] == "CPU usage high"
    assert alert["severity"] == "critical"
    assert alert["metric_name"] == "cpu_utilization"


def test_list_alerts(client: TestClient):
    client.post("/alerts/", json=_alert_payload())

    response = client.get("/alerts/")

    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 1
    assert alerts[0]["title"] == "CPU usage high"


def test_get_alert_by_id(client: TestClient):
    created = client.post("/alerts/", json=_alert_payload()).json()

    response = client.get(f"/alerts/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["severity"] == "critical"


def test_explain_alert(client: TestClient):
    created = client.post("/alerts/", json=_alert_payload()).json()

    response = client.post(f"/alerts/{created['id']}/explain")

    assert response.status_code == 200
    result = response.json()
    assert result["alert_id"] == created["id"]
    assert "critical" in result["explanation"].lower()
    assert "cpu_utilization" in result["explanation"]
    datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))


# --- Edge cases added manually ---
def _create_alert(client: TestClient, **overrides: str | float) -> dict:
    """Create an alert through the API and return its JSON response."""
    payload: dict[str, str | float] = {
        "title": "Test alert",
        "severity": "warning",
        "source": "test-source",
        "metric_name": "test_metric",
        "metric_value": 50.0,
        "threshold": 40.0,
    }
    payload.update(overrides)
    response = client.post("/alerts", json=payload)
    assert response.status_code == 201
    return response.json()


def test_explain_alert_for_nonexistent_id_returns_404(client: TestClient) -> None:
    response = client.post("/alerts/999/explain")

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found"


def test_explain_alert_when_metric_is_below_threshold(
    client: TestClient,
) -> None:
    alert = _create_alert(
        client,
        title="Connection pool below minimum",
        severity="warning",
        source="db-pool",
        metric_name="active_connections",
        metric_value=2,
        threshold=10,
    )

    response = client.post(f"/alerts/{alert['id']}/explain")

    assert response.status_code == 200
    assert "fell below its threshold" in response.json()["explanation"]


def test_explain_alert_with_zero_threshold_does_not_crash(
    client: TestClient,
) -> None:
    alert = _create_alert(
        client,
        title="Unexpected traffic on idle endpoint",
        severity="info",
        source="edge-cache",
        metric_name="request_count",
        metric_value=5,
        threshold=0,
    )

    response = client.post(f"/alerts/{alert['id']}/explain")

    assert response.status_code == 200
    assert "threshold of 0.0" in response.json()["explanation"]
