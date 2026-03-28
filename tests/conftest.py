"""Shared pytest fixtures for the Schwab Options MCP Server tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data.cache import CacheManager
from src.data.schwab_client import SchwabClient
from src.data.token_manager import TokenManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def spx_quote_response() -> dict:
    """Load the SPX quote fixture from JSON.

    Returns the raw Schwab API response shape for a single SPX quote.
    """
    with open(FIXTURES_DIR / "spx_quote_response.json") as f:
        return json.load(f)


@pytest.fixture
def spx_chain_response() -> dict:
    """Load the SPX options chain fixture from JSON.

    Returns the raw Schwab API response shape for an SPX options chain
    with 3 strikes (5850, 5900, 5950) at 7 DTE.
    """
    with open(FIXTURES_DIR / "spx_chain_response.json") as f:
        return json.load(f)


@pytest.fixture
def mock_schwabdev_client() -> MagicMock:
    """Create a mock schwabdev.Client instance.

    Mocks the actual schwabdev.Client that makes HTTP calls to Schwab API.
    Configure return values per test as needed.
    """
    client = MagicMock()
    client.update_tokens.return_value = True
    return client


@pytest.fixture
def mock_token_manager(mock_schwabdev_client: MagicMock) -> TokenManager:
    """Create a TokenManager that returns the mock schwabdev.Client.

    Bypasses actual OAuth token handling and returns the mock client
    so tests never hit the real Schwab API.
    """
    manager = TokenManager(
        app_key="test_key",
        app_secret="test_secret",
        callback_url="https://127.0.0.1:8182",
        token_path="./test_tokens.db",
    )
    manager._client = mock_schwabdev_client
    return manager


@pytest.fixture
def cache_manager(tmp_path: Path) -> CacheManager:
    """Create a CacheManager using a temporary directory.

    Each test gets a fresh, isolated cache that is automatically
    cleaned up after the test completes.
    """
    return CacheManager(cache_dir=str(tmp_path / "cache"))


@pytest.fixture
def schwab_client(mock_token_manager: TokenManager, cache_manager: CacheManager) -> SchwabClient:
    """Create a SchwabClient wired to mock token manager and temp cache.

    This is the main fixture for testing the Schwab client wrapper.
    The underlying schwabdev.Client is mocked — no real API calls.
    """
    return SchwabClient(
        token_manager=mock_token_manager,
        cache=cache_manager,
        max_retries=1,
        retry_base_delay=0.01,
    )
