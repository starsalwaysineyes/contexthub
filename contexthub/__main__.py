from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import uvicorn

from contexthub.app import create_app
from contexthub.config import load_config
from contexthub.env import load_env_files
from contexthub.importer import ImportMarkdownOptions, import_markdown_tree, parse_derive_layers, print_import_summary


def main() -> None:
    parser = argparse.ArgumentParser(prog="contexthub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the ContextHub API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    import_markdown = subparsers.add_parser("import-markdown", help="Import a Markdown tree into ContextHub")
    import_markdown.add_argument("--base-url", default=os.environ.get("CONTEXT_HUB_BASE_URL", "http://127.0.0.1:4040"))
    import_markdown.add_argument("--token", default=os.environ.get("CONTEXT_HUB_TOKEN"))
    import_markdown.add_argument("--tenant-id", required=True)
    import_markdown.add_argument("--partition-key", required=True)
    import_markdown.add_argument("--layer", choices=["l0", "l1", "l2"], required=True)
    import_markdown.add_argument("--root", required=True)
    import_markdown.add_argument("--limit", type=int, default=None)
    import_markdown.add_argument("--derive-layers", default="")
    import_markdown.add_argument("--prompt-preset", default="archive_and_memory")
    import_markdown.add_argument("--derive-mode", choices=["sync", "async"], default="sync")
    import_markdown.add_argument("--type", dest="record_type", default="resource")
    import_markdown.add_argument("--source-kind", default="markdown_file")
    import_markdown.add_argument("--relative-path-prefix", default="")
    import_markdown.add_argument("--metadata-json", default="{}")
    import_markdown.add_argument("--include", action="append", default=[])
    import_markdown.add_argument("--exclude", action="append", default=[])
    import_markdown.add_argument("--tag", action="append", default=[])
    import_markdown.add_argument("--dry-run", action="store_true")

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
        return

    if args.command == "import-markdown":
        load_env_files()
        options = ImportMarkdownOptions(
            base_url=args.base_url,
            token=args.token,
            tenant_id=args.tenant_id,
            partition_key=args.partition_key,
            layer=args.layer,
            root=Path(args.root),
            file_limit=args.limit,
            derive_layers=parse_derive_layers(args.derive_layers),
            prompt_preset=args.prompt_preset,
            derive_mode=args.derive_mode,
            record_type=args.record_type,
            source_kind=args.source_kind,
            relative_path_prefix=args.relative_path_prefix or None,
            metadata=json.loads(args.metadata_json),
            include_globs=tuple(args.include),
            exclude_globs=tuple(args.exclude),
            dry_run=args.dry_run,
            tags=tuple(args.tag),
        )
        print_import_summary(import_markdown_tree(options))
        return


if __name__ == "__main__":
    main()
