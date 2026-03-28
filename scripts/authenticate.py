"""Auto-capture OAuth 2.0 authentication for Schwab API.

Eliminates the copy-paste step from schwabdev's default flow by running
a local HTTPS callback server that auto-captures the auth code.

Usage:
    python scripts/authenticate.py

Flow:
    1. Generates self-signed HTTPS cert (first run only)
    2. Starts local HTTPS server on callback URL
    3. Opens browser to Schwab OAuth login
    4. User logs in (manual — Schwab requires it)
    5. Schwab redirects to callback → server auto-captures auth code
    6. Exchanges code for tokens via schwabdev
    7. Saves tokens to disk
"""

import os
import ssl
import subprocess
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

APP_KEY = os.environ.get("SCHWAB_APP_KEY", "")
APP_SECRET = os.environ.get("SCHWAB_APP_SECRET", "")
CALLBACK_URL = os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
TOKEN_PATH = os.environ.get("TOKEN_PATH", "./tokens/schwab_tokens.db")

CERT_DIR = PROJECT_ROOT / "certs"
CERT_FILE = CERT_DIR / "localhost.pem"
KEY_FILE = CERT_DIR / "localhost-key.pem"


def generate_self_signed_cert() -> None:
    """Generate a self-signed certificate for the local HTTPS callback server."""
    if CERT_FILE.exists() and KEY_FILE.exists():
        print("[OK] Self-signed certificate already exists")
        return

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    print("[...] Generating self-signed certificate for localhost...")

    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE),
            "-out", str(CERT_FILE),
            "-days", "365",
            "-nodes",
            "-subj", "/CN=127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    print("[OK] Certificate generated")


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback and extracts the auth code."""

    auth_url: str | None = None

    def do_GET(self):
        """Handle the OAuth callback redirect."""
        # Store the full callback URL for schwabdev
        CallbackHandler.auth_url = f"{CALLBACK_URL}{self.path}"

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authentication successful!</h2>"
            b"<p>You can close this tab and return to the terminal.</p>"
            b"</body></html>"
        )

        # Shut down the server after handling the callback
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass


def start_callback_server() -> str:
    """Start a local HTTPS server and wait for the OAuth callback.

    Returns the full callback URL with auth code.
    """
    parsed = urlparse(CALLBACK_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8182

    server = HTTPServer((host, port), CallbackHandler)

    # Wrap with SSL
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
    server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)

    print(f"[...] Listening for OAuth callback on {CALLBACK_URL}")
    server.serve_forever()

    if CallbackHandler.auth_url is None:
        print("[ERROR] No callback received")
        sys.exit(1)

    return CallbackHandler.auth_url


def main() -> None:
    if not APP_KEY or not APP_SECRET:
        print("[ERROR] SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in .env")
        sys.exit(1)

    # Step 1: Ensure self-signed cert exists
    generate_self_signed_cert()

    # Step 2: Build the Schwab OAuth URL
    auth_url = (
        f"https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={APP_KEY}"
        f"&redirect_uri={CALLBACK_URL}"
    )

    # Step 3: Start callback server in background thread
    server_thread = threading.Thread(target=lambda: None, daemon=True)
    callback_url_result = [None]

    def run_server():
        callback_url_result[0] = start_callback_server()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Step 4: Open browser
    print(f"\n[...] Opening browser for Schwab login...")
    print(f"      If the browser doesn't open, visit:\n      {auth_url}\n")
    webbrowser.open(auth_url)

    # Step 5: Wait for callback
    server_thread.join(timeout=300)  # 5 minute timeout

    if callback_url_result[0] is None:
        print("[ERROR] Timed out waiting for OAuth callback (5 minutes)")
        sys.exit(1)

    callback_with_code = callback_url_result[0]
    print(f"[OK] Captured OAuth callback")

    # Step 6: Exchange code for tokens using schwabdev
    import schwabdev

    token_path = Path(TOKEN_PATH)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    print("[...] Exchanging auth code for tokens...")

    try:
        client = schwabdev.Client(
            app_key=APP_KEY,
            app_secret=APP_SECRET,
            callback_url=CALLBACK_URL,
            tokens_db=str(token_path),
            timeout=10,
            # Pass a custom auth handler that returns our captured URL
            call_on_auth=lambda: callback_with_code,
        )
        # Force token update to verify everything works
        client.update_tokens()
        print(f"\n[OK] Tokens saved to {token_path}")
        print("[OK] Authentication complete! The MCP server can now access Schwab data.")
        print("\n     Token validity:")
        print("       Access token:  30 minutes (auto-refreshes)")
        print("       Refresh token: 7 days (re-run this script when it expires)")
    except Exception as e:
        print(f"\n[ERROR] Token exchange failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
