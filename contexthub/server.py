from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("CONTEXT_HUB_BIND_HOST", "127.0.0.1")
    port = int(os.getenv("CONTEXT_HUB_PORT", "4040"))
    uvicorn.run("contexthub.app:create_app", host=host, port=port, factory=True)


if __name__ == "__main__":
    main()
