from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partitions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  key TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  allow_cross_query_from TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  UNIQUE (tenant_id, key),
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS principals (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  metadata TEXT NOT NULL DEFAULT '{}',
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS principal_partition_acl (
  id TEXT PRIMARY KEY,
  principal_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  can_read INTEGER NOT NULL DEFAULT 1,
  can_write INTEGER NOT NULL DEFAULT 0,
  allowed_layers TEXT NOT NULL DEFAULT '["l0","l1","l2"]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (principal_id, partition_key),
  FOREIGN KEY (principal_id) REFERENCES principals (id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  type TEXT NOT NULL,
  layer TEXT NOT NULL DEFAULT 'l1',
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}',
  manual_summary TEXT NOT NULL DEFAULT '',
  importance REAL NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  idempotency_key TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (tenant_id, partition_key, idempotency_key),
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  vector TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (record_id) REFERENCES records (id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  agent_id TEXT,
  summary TEXT NOT NULL DEFAULT '',
  metadata TEXT NOT NULL DEFAULT '{}',
  messages TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
  FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS derivation_jobs (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  status TEXT NOT NULL,
  mode TEXT NOT NULL,
  effective_mode TEXT,
  requested_layers TEXT NOT NULL DEFAULT '[]',
  provider TEXT NOT NULL,
  model TEXT,
  prompt_preset TEXT NOT NULL,
  error_message TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
  FOREIGN KEY (source_record_id) REFERENCES records (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_links (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  target_record_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE (source_record_id, target_record_id, relation),
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
  FOREIGN KEY (source_record_id) REFERENCES records (id) ON DELETE CASCADE,
  FOREIGN KEY (target_record_id) REFERENCES records (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_partitions_tenant_key ON partitions (tenant_id, key);
CREATE INDEX IF NOT EXISTS idx_principals_tenant_id ON principals (tenant_id);
CREATE INDEX IF NOT EXISTS idx_acl_principal_partition ON principal_partition_acl (principal_id, partition_key);
CREATE INDEX IF NOT EXISTS idx_records_tenant_partition ON records (tenant_id, partition_key);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant_partition ON chunks (tenant_id, partition_key);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_partition ON sessions (tenant_id, partition_key);
CREATE INDEX IF NOT EXISTS idx_derivation_jobs_tenant_partition ON derivation_jobs (tenant_id, partition_key);
CREATE INDEX IF NOT EXISTS idx_derivation_jobs_source_record ON derivation_jobs (source_record_id);
CREATE INDEX IF NOT EXISTS idx_record_links_source_record ON record_links (source_record_id);
CREATE INDEX IF NOT EXISTS idx_record_links_target_record ON record_links (target_record_id);
"""


class SQLiteStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            self._apply_migrations(conn)

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        record_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(records)").fetchall()
        }
        if "layer" not in record_columns:
            conn.execute("ALTER TABLE records ADD COLUMN layer TEXT NOT NULL DEFAULT 'l1'")

        if not self._records_idempotency_is_partition_scoped(conn):
            self._rebuild_records_table_with_partition_scoped_idempotency(conn)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_tenant_partition ON records (tenant_id, partition_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_tenant_partition_layer ON records (tenant_id, partition_key, layer)"
        )

    def _records_idempotency_is_partition_scoped(self, conn: sqlite3.Connection) -> bool:
        indexes = conn.execute("PRAGMA index_list(records)").fetchall()
        for index in indexes:
            if not index["unique"]:
                continue
            columns = [
                row["name"]
                for row in conn.execute(f"PRAGMA index_info({index['name']!r})").fetchall()
            ]
            if columns == ["tenant_id", "partition_key", "idempotency_key"]:
                return True
        return False

    def _rebuild_records_table_with_partition_scoped_idempotency(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            """
            CREATE TABLE records_new (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              partition_key TEXT NOT NULL,
              type TEXT NOT NULL,
              layer TEXT NOT NULL DEFAULT 'l1',
              title TEXT NOT NULL,
              text TEXT NOT NULL,
              source TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              metadata TEXT NOT NULL DEFAULT '{}',
              manual_summary TEXT NOT NULL DEFAULT '',
              importance REAL NOT NULL DEFAULT 0,
              pinned INTEGER NOT NULL DEFAULT 0,
              idempotency_key TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (tenant_id, partition_key, idempotency_key),
              FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
            );

            INSERT INTO records_new (
              id, tenant_id, partition_key, type, layer, title, text, source, tags, metadata,
              manual_summary, importance, pinned, idempotency_key, created_at, updated_at
            )
            SELECT
              id, tenant_id, partition_key, type, layer, title, text, source, tags, metadata,
              manual_summary, importance, pinned, idempotency_key, created_at, updated_at
            FROM records;

            DROP TABLE records;
            ALTER TABLE records_new RENAME TO records;
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def counts(self) -> dict[str, int]:
        tables = [
            "tenants",
            "partitions",
            "agents",
            "principals",
            "principal_partition_acl",
            "records",
            "chunks",
            "sessions",
            "derivation_jobs",
            "record_links",
        ]
        with self.connection() as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def from_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
