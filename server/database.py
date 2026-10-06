"""SQLite connection and schema initialization for Navi application data."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3


DATABASE_PATH_ENV = "NAVI_DATABASE_PATH"


CHAT_ITEM_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_item (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 100),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    activity_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_item_activity_time
ON chat_item(activity_time DESC);
"""

CHAT_CONTENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_content (
    content_id TEXT PRIMARY KEY NOT NULL,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('generating', 'completed', 'failed')),
    created_time TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chat_item(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_content_chat_created_time
ON chat_content(chat_id, created_time DESC);
"""

MODEL_SETTING_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_setting (
    setting_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL UNIQUE
        CHECK (length(trim(name)) BETWEEN 1 AND 100),
    model_provider TEXT NOT NULL DEFAULT 'openai'
        CHECK (length(trim(model_provider)) BETWEEN 1 AND 64),
    model_name TEXT NOT NULL
        CHECK (length(trim(model_name)) BETWEEN 1 AND 200),
    api_key TEXT NOT NULL
        CHECK (length(trim(api_key)) > 0),
    base_url TEXT NOT NULL
        CHECK (length(trim(base_url)) BETWEEN 1 AND 2048),
    active INTEGER NOT NULL DEFAULT 0
        CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_model_setting_one_active
ON model_setting(active)
WHERE active = 1;
"""


def get_database_path() -> Path:
    """Return Navi's SQLite path under the current user's local app data."""
    override = os.getenv(DATABASE_PATH_ENV)
    if override:
        return Path(override).expanduser().resolve()

    local_app_data = os.getenv("LOCALAPPDATA")
    base_directory = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base_directory / "Navi" / "navi.db"


def connect_database(database_path: Path | None = None) -> sqlite3.Connection:
    """Open one configured SQLite connection and enable required safeguards."""
    path = database_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: Path | None = None) -> Path:
    """Create the database file, chat_item table and indexes when absent."""
    path = database_path or get_database_path()
    with closing(connect_database(path)) as connection:
        # WAL allows GUI-triggered reads while the server is committing a write.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(CHAT_ITEM_SCHEMA)
        connection.executescript(CHAT_CONTENT_SCHEMA)
        connection.executescript(MODEL_SETTING_SCHEMA)
        connection.commit()
    return path
