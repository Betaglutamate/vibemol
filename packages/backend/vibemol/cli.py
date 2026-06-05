"""Command-line entry point: ``vibemol serve``."""

from __future__ import annotations

import argparse

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vibemol", description="VibeMol molecular viewer")
    parser.add_argument("--version", action="version", version=f"vibemol {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the VibeMol web server")
    serve.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes")

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        # Pass an import string so --reload works; the app factory builds the FastAPI app.
        uvicorn.run(
            "vibemol.server.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
