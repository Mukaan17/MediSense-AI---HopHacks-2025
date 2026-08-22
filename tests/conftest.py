import os
import sys

# Tests run against demo mode with fast startup; individual modules that
# need clinical mode reload the app themselves.
os.environ.setdefault("APP_MODE", "demo")
os.environ.setdefault("SKIP_HASH", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from api.server import app
    return TestClient(app)
