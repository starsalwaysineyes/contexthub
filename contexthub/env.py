from __future__ import annotations

import os
from pathlib import Path


def _load_single_env_file(file_path: Path) -> None:
    if not file_path.exists():
        return

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def load_env_files() -> None:
    explicit_path = os.environ.get("CONTEXT_HUB_ENV_FILE")
    if explicit_path:
        _load_single_env_file(Path(explicit_path).expanduser().resolve())
        return

    root = Path.cwd()
    for candidate in (root / ".env.local", root / ".env"):
        _load_single_env_file(candidate)
