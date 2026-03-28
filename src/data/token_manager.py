"""OAuth 2.0 token lifecycle management wrapping schwabdev."""

from pathlib import Path

import schwabdev

from src.shared.logging import get_logger

logger = get_logger(__name__)


class TokenError(Exception):
    """Raised when tokens are invalid or expired."""


class RefreshTokenExpired(TokenError):
    """Raised when the refresh token has expired and re-authentication is needed."""

    def __init__(self):
        super().__init__(
            "Schwab refresh token has expired (7-day limit). "
            "Please re-authenticate by running: python scripts/authenticate.py"
        )


class TokenManager:
    """Manages Schwab OAuth 2.0 tokens via schwabdev.

    Wraps schwabdev.Client's built-in token handling with:
    - Clear error messages for expired refresh tokens
    - Token path configuration
    - Client factory method
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        callback_url: str = "https://127.0.0.1:8182",
        token_path: str = "./tokens/schwab_tokens.db",
    ):
        self._app_key = app_key
        self._app_secret = app_secret
        self._callback_url = callback_url
        self._token_path = Path(token_path)
        self._client: schwabdev.Client | None = None

    def _ensure_token_dir(self) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)

    def get_client(self) -> schwabdev.Client:
        """Get or create a schwabdev Client with auto-refreshing tokens.

        Raises RefreshTokenExpired if the refresh token has expired.
        """
        if self._client is not None:
            return self._client

        self._ensure_token_dir()

        if not self._token_path.exists():
            raise TokenError(
                "No tokens found. Please authenticate first by running: "
                "python scripts/authenticate.py"
            )

        try:
            client = schwabdev.Client(
                app_key=self._app_key,
                app_secret=self._app_secret,
                callback_url=self._callback_url,
                tokens_db=str(self._token_path),
                timeout=10,
            )
            # schwabdev auto-refreshes on API calls, but let's verify tokens load
            client.update_tokens()
            self._client = client
            logger.info("Schwab client initialized with valid tokens")
            return client
        except Exception as e:
            error_msg = str(e).lower()
            if "refresh" in error_msg or "expired" in error_msg or "auth" in error_msg:
                raise RefreshTokenExpired() from e
            raise TokenError(f"Failed to initialize Schwab client: {e}") from e

    def refresh(self) -> bool:
        """Force a token refresh. Returns True if successful."""
        try:
            client = self.get_client()
            return client.update_tokens(force_access_token=True)
        except RefreshTokenExpired:
            raise
        except Exception as e:
            logger.error("Token refresh failed: %s", e)
            return False
