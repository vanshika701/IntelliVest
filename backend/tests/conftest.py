import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    # Using the context-manager form runs the app's lifespan (connects to
    # Mongo on entry, closes it on exit) instead of just importing the app.
    with TestClient(app) as test_client:
        yield test_client
