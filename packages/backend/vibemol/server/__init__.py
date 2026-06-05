"""The VibeMol web server (FastAPI app + WebSocket hub)."""

from .app import create_app

__all__ = ["create_app"]
