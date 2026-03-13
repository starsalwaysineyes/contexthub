from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
SKIP_DIRS = {".git", ".venv", "node_modules", "var"}
SKIP_FILES = {"uv.lock"}
PATTERNS = [
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}")),
]


def iter_files(root: Path):
    for dir_path, dir_names, file_names in os.walk(root, topdown=True):
        dir_names[:] = [name for name in dir_names if name not in SKIP_DIRS]

        for file_name in file_names:
            if file_name in SKIP_FILES:
                continue

            yield Path(dir_path) / file_name


def line_number_at(content: str, index: int) -> int:
    return content.count("\n", 0, index) + 1


def main() -> int:
    violations: list[tuple[str, int, str, str]] = []

    for file_path in iter_files(ROOT):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for name, pattern in PATTERNS:
            for match in pattern.finditer(content):
                line = line_number_at(content, match.start())
                masked = match.group(0)[:16] + "..."
                violations.append((str(file_path.relative_to(ROOT)), line, name, masked))

    if not violations:
        print("Secret scan passed.")
        return 0

    print("Potential secrets detected:", file=sys.stderr)
    for rel, line, kind, masked in violations:
        print(f"- {rel}:{line} {kind} {masked}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
