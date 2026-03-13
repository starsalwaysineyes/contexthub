from __future__ import annotations

import argparse

import uvicorn

from contexthub.app import create_app
from contexthub.config import load_config
from contexthub.env import load_env_files


def main() -> None:
    parser = argparse.ArgumentParser(prog="contexthub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the ContextHub API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    args = parser.parse_args()

    if args.command == "serve":
        load_env_files()
        config = load_config()
        uvicorn.run(
            "contexthub.app:create_app",
            factory=True,
            host=args.host,
            port=args.port or config.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
