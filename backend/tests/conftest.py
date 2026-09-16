import os
import tempfile
from pathlib import Path

import pytest

_DB = Path(tempfile.gettempdir()) / "medorchestra_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["ANTHROPIC_API_KEY"] = ""  # tests always use the local NLP pipeline
os.environ["AGENT_STEP_DELAY"] = "0"
os.environ["FLEET_TRACKER"] = "0"  # tests drive ambulances stage by stage
os.environ["TELEMETRY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import reset_and_seed  # noqa: E402


@pytest.fixture(scope="session")
def client():
    reset_and_seed()
    with TestClient(app) as c:
        yield c


def _token(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _token(client, "admin", "admin123")


@pytest.fixture(scope="session")
def doctor(client):
    return _token(client, "doctor", "doctor123")


@pytest.fixture(scope="session")
def nurse(client):
    return _token(client, "nurse", "nurse123")


@pytest.fixture(scope="session")
def patient_user(client):
    return _token(client, "patient", "patient123")
