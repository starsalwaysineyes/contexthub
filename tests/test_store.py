from __future__ import annotations

import sqlite3
from pathlib import Path

from contexthub.store import SQLiteStore


OLD_SCHEMA = """
CREATE TABLE tenants (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE partitions (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  key TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  allow_cross_query_from TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  UNIQUE (tenant_id, key)
);

CREATE TABLE records (
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
  UNIQUE (tenant_id, idempotency_key)
);
"""


def test_store_migrates_record_idempotency_to_partition_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "contexthub.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(OLD_SCHEMA)
    conn.close()

    store = SQLiteStore(db_path)
    store.init()

    with store.connection() as conn:
        indexes = conn.execute("PRAGMA index_list(records)").fetchall()
        unique_indexes = [index for index in indexes if index[2]]
        assert unique_indexes
        matched = False
        for index in unique_indexes:
            columns = [row[2] for row in conn.execute(f"PRAGMA index_info('{index[1]}')").fetchall()]
            if columns == ["tenant_id", "partition_key", "idempotency_key"]:
                matched = True
                break
        assert matched is True
