import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add the backend directory to Python path so relative imports work
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from main import app


# Mark integration tests that require a running backend
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as requiring a running backend server"
    )


def pytest_collection_modifyitems(config, items):
    """Mark test files as integration tests if they require backend."""
    # Files that need a live backend
    integration_test_files = {
        "test_simulation_integration.py",
        "test_integration_features.py",
    }

    for item in items:
        if any(integration_file in str(item.fspath) for integration_file in integration_test_files):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    # TestClient in FastAPI 0.100+ should trigger lifespan events
    with TestClient(app) as client:
        yield client
