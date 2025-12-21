"""
Integration test fixtures.

These fixtures set up real database connections and verify
cross-component interactions.
"""

import os
import pytest

# Mark all tests in this directory as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def integration_db_url():
    """
    Get integration test database URL.

    Integration tests use a separate database to avoid
    interfering with development data.
    """
    url = os.environ.get(
        "INTEGRATION_DATABASE_URL",
        os.environ.get("TEST_DATABASE_URL", "postgresql://predict:predict@localhost:5433/predict")
    )
    return url


@pytest.fixture(scope="module")
async def integration_db(integration_db_url):
    """
    Module-scoped database for integration tests.

    Creates tables if they don't exist.
    """
    from polymarket_bot.storage import Database, DatabaseConfig

    config = DatabaseConfig(url=integration_db_url)
    database = Database(config)
    await database.initialize()

    yield database

    await database.close()
