"""Entry point for the israelgrocery MCP package."""
import sys
from pathlib import Path

# Make sure src/ is on the path when running as a package entry point
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import main  # noqa: E402

__all__ = ["main"]
