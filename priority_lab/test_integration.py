import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Alert
from priority_score import calculate_priority_score


@pytest.fixture
def test_context():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_alert_priority_returns_calculated_score(test_context):
    client, session_factory = test_context
    with session_factory() as db:
        alert = Alert(severity="critical", metric_value=125, threshold=100)
        db.add(alert)
        db.commit()
        db.refresh(alert)
        alert_id = alert.id
        expected_score = calculate_priority_score(
            alert.severity,
            alert.metric_value,
            alert.threshold,
        )

    response = client.get(f"/alerts/{alert_id}/priority")

    assert response.status_code == 200
    assert response.json() == {
        "alert_id": alert_id,
        "priority_score": expected_score,
    }


def test_nonexistent_alert_returns_404(test_context):
    client, _ = test_context

    response = client.get("/alerts/999999/priority")

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found"


# --- Edge case added manually ---
def test_zero_threshold_alert_returns_422(test_context):
    client, session_factory = test_context
    with session_factory() as db:
        alert = Alert(severity="warning", metric_value=50, threshold=0)
        db.add(alert)
        db.commit()
        alert_id = alert.id

    response = client.get(f"/alerts/{alert_id}/priority")

    assert response.status_code == 422
    assert "threshold must not be zero" in response.json()["detail"]
