"""Tests for src/data/token_manager.py — OAuth 2.0 token lifecycle.

Verifies token manager correctly wraps schwabdev, handles missing tokens,
detects expired refresh tokens, and provides clear error messages.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data.token_manager import RefreshTokenExpired, TokenError, TokenManager


class TestTokenManagerGetClient:
    """Tests for TokenManager.get_client()."""

    def test_get_client_returns_schwabdev_client(
        self, mock_schwabdev_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test that get_client() returns a working schwabdev.Client.

        When tokens exist and are valid, get_client should return a client
        that can make API calls.
        """
        token_db = tmp_path / "tokens.db"
        token_db.touch()  # simulate existing token file

        manager = TokenManager(
            app_key="test_key",
            app_secret="test_secret",
            token_path=str(token_db),
        )
        manager._client = mock_schwabdev_client

        client = manager.get_client()
        assert client is mock_schwabdev_client

    def test_get_client_caches_client_instance(
        self, mock_schwabdev_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test that get_client() returns the same instance on repeated calls.

        The client should be created once and reused, not recreated each time.
        """
        manager = TokenManager(
            app_key="test_key",
            app_secret="test_secret",
            token_path=str(tmp_path / "tokens.db"),
        )
        manager._client = mock_schwabdev_client

        client1 = manager.get_client()
        client2 = manager.get_client()
        assert client1 is client2

    def test_get_client_raises_token_error_when_no_tokens(self, tmp_path: Path) -> None:
        """Test that get_client() raises TokenError when token file doesn't exist.

        User must run authenticate.py first. The error message should tell them how.
        """
        manager = TokenManager(
            app_key="test_key",
            app_secret="test_secret",
            token_path=str(tmp_path / "nonexistent_tokens.db"),
        )

        with pytest.raises(TokenError, match="No tokens found"):
            manager.get_client()

    def test_get_client_raises_refresh_token_expired(self, tmp_path: Path) -> None:
        """Test that get_client() raises RefreshTokenExpired when refresh token is invalid.

        When schwabdev raises an auth-related error during token update,
        TokenManager should wrap it in RefreshTokenExpired with a clear message.
        """
        token_db = tmp_path / "tokens.db"
        token_db.touch()

        with patch("schwabdev.Client") as mock_cls:
            mock_cls.return_value.update_tokens.side_effect = Exception("refresh token expired")
            manager = TokenManager(
                app_key="test_key",
                app_secret="test_secret",
                token_path=str(token_db),
            )

            with pytest.raises(RefreshTokenExpired, match="authenticate.py"):
                manager.get_client()


class TestTokenManagerRefresh:
    """Tests for TokenManager.refresh()."""

    def test_refresh_calls_update_tokens(
        self, mock_schwabdev_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test that refresh() calls schwabdev's update_tokens with force flag.

        This forces a token refresh even if the current token hasn't expired.
        """
        manager = TokenManager(
            app_key="test_key",
            app_secret="test_secret",
            token_path=str(tmp_path / "tokens.db"),
        )
        manager._client = mock_schwabdev_client
        mock_schwabdev_client.update_tokens.return_value = True

        result = manager.refresh()
        assert result is True
        mock_schwabdev_client.update_tokens.assert_called_with(force_access_token=True)

    def test_refresh_returns_false_on_failure(
        self, mock_schwabdev_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test that refresh() returns False when token update fails.

        Non-auth errors should not raise — just return False.
        """
        manager = TokenManager(
            app_key="test_key",
            app_secret="test_secret",
            token_path=str(tmp_path / "tokens.db"),
        )
        manager._client = mock_schwabdev_client
        mock_schwabdev_client.update_tokens.side_effect = RuntimeError("network error")

        result = manager.refresh()
        assert result is False


class TestRefreshTokenExpired:
    """Tests for the RefreshTokenExpired exception."""

    def test_error_message_includes_instructions(self) -> None:
        """Test that RefreshTokenExpired message tells user to run authenticate.py.

        The error message is user-facing — Claude shows it directly.
        """
        error = RefreshTokenExpired()
        assert "authenticate.py" in str(error)
        assert "7-day" in str(error)
