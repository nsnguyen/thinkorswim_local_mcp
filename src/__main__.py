"""Allow running as `python -m src`."""

from src.server import mcp

mcp.run("stdio")
