CREATE TABLE IF NOT EXISTS workspaces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  workspace_kind TEXT NOT NULL,
  agent_id TEXT NOT NULL DEFAULT '',
  root_uri TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, workspace_kind, agent_id)
);

CREATE TABLE IF NOT EXISTS fs_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  workspace_kind TEXT NOT NULL,
  agent_id TEXT NOT NULL DEFAULT '',
  relative_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT,
  content_text TEXT,
  content_hash TEXT,
  size_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, workspace_kind, agent_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_fs_entries_scope_path
  ON fs_entries(user_id, workspace_kind, agent_id, relative_path);

CREATE TABLE IF NOT EXISTS search_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  chunk_text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(entry_id) REFERENCES fs_entries(id) ON DELETE CASCADE,
  UNIQUE(entry_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_search_chunks_entry
  ON search_chunks(entry_id);
