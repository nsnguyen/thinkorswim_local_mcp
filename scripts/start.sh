#!/usr/bin/env bash
# Setup (if needed) and start the MCP server.
# Usage: bash scripts/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

cd "$PROJECT_DIR"

# ── Python check ────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major="${version%%.*}"
        minor="${version#*.}"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.11+ is required but not found."
    exit 1
fi

# ── Virtual environment ─────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "[...] Creating virtual environment ($($PYTHON --version))..."
    "$PYTHON" -m venv "$VENV_DIR"
    echo "[OK] Created .venv"
fi

# ── Install / update dependencies ───────────────────────────────────
echo "[...] Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r requirements.txt -q
echo "[OK] Dependencies installed"

# ── .env file ───────────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "[ACTION REQUIRED] .env created from template — edit it with your Schwab credentials:"
    echo "  SCHWAB_APP_KEY=your_app_key"
    echo "  SCHWAB_APP_SECRET=your_app_secret"
    echo ""
    echo "Then re-run: bash scripts/start.sh"
    exit 1
fi

# ── Start server ────────────────────────────────────────────────────
exec "$VENV_DIR/bin/python" -m src
