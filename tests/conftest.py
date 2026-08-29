"""
pytest configuration and fixtures
"""
import pytest

# Configure pytest-asyncio
pytest_plugins = ['pytest_asyncio']


@pytest.fixture(scope="function")
def anyio_backend():
    return 'asyncio'
