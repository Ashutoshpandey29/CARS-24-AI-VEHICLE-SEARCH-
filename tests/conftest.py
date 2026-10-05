import os

import pytest

# tests run against the rule parser so they are deterministic and need no network
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("REDIS_URL", None)


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("data") / "cars.db"
    os.environ["DB_PATH"] = str(db)

    from fastapi.testclient import TestClient

    from app.cache import get_cache
    from app.config import get_settings
    from app.main import app
    from scripts.seed import seed

    get_settings.cache_clear()
    get_cache().clear()
    seed(600, str(db))
    with TestClient(app) as c:
        yield c
