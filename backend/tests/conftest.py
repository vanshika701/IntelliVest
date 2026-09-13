import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.core.config import settings
from app.data.indexes import ensure_indexes
from app.data.mongo import close_mongo_connection, connect_to_mongo, get_database
from app.main import app

TEST_DB_NAME = "intellivest_test"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Scheduler off: a real AsyncIOScheduler can't cleanly restart across
    # multiple tests' TestClient lifespans, and nothing here needs actual
    # scheduled ingestion running — see test_scheduler.py for that.
    monkeypatch.setattr(settings, "enable_scheduler", False)

    # Using the context-manager form runs the app's lifespan (connects to
    # Mongo on entry, closes it on exit) instead of just importing the app.
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def mongo_test_db(monkeypatch: pytest.MonkeyPatch):
    """A real, isolated MongoDB database for data-layer integration tests.

    Isolated from the dev database (a separate DB name on the same Mongo
    instance) so tests never pollute or depend on real dev data, and
    dropped after every test so re-running the suite doesn't accumulate
    leftover documents.

    Connects directly via connect_to_mongo() rather than going through
    TestClient — this fixture is for testing the data layer itself, and
    running it in the same event loop pytest-asyncio gives the test
    avoids the separate event loop TestClient drives for the app lifespan.
    """
    monkeypatch.setattr(settings, "mongodb_db_name", TEST_DB_NAME)

    await connect_to_mongo()
    await ensure_indexes()

    yield get_database()

    await get_database().client.drop_database(TEST_DB_NAME)
    await close_mongo_connection()
