"""SQLite 数据库路径与表结构测试。"""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.database import get_database_path, initialize_database


class DatabaseTests(unittest.TestCase):
    def test_default_path_uses_local_app_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"LOCALAPPDATA": directory},
            clear=False,
        ):
            os.environ.pop("NAVI_DATABASE_PATH", None)
            self.assertEqual(
                get_database_path(),
                Path(directory) / "Navi" / "navi.db",
            )

    def test_initialize_creates_chat_item_table_and_activity_index(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "Navi" / "navi.db"
            self.assertEqual(initialize_database(database_path), database_path)
            self.assertTrue(database_path.is_file())

            with closing(sqlite3.connect(database_path)) as connection:
                columns = {
                    row[1]: row[2]
                    for row in connection.execute("PRAGMA table_info(chat_item)")
                }
                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(chat_item)")
                }

            self.assertEqual(
                columns,
                {
                    "id": "TEXT",
                    "name": "TEXT",
                    "created_at": "TEXT",
                    "updated_at": "TEXT",
                    "activity_time": "TEXT",
                },
            )
            self.assertIn("idx_chat_item_activity_time", indexes)

    def test_initialize_creates_chat_content_table_foreign_key_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "Navi" / "navi.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                columns = {
                    row[1]: row[2]
                    for row in connection.execute("PRAGMA table_info(chat_content)")
                }
                foreign_keys = connection.execute(
                    "PRAGMA foreign_key_list(chat_content)"
                ).fetchall()
                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(chat_content)")
                }

            self.assertEqual(
                columns,
                {
                    "content_id": "TEXT",
                    "chat_id": "TEXT",
                    "role": "TEXT",
                    "content": "TEXT",
                    "status": "TEXT",
                    "created_time": "TEXT",
                },
            )
            self.assertTrue(
                any(
                    row[2] == "chat_item"
                    and row[3] == "chat_id"
                    and row[4] == "id"
                    and row[6] == "CASCADE"
                    for row in foreign_keys
                )
            )
            self.assertIn("idx_chat_content_chat_created_time", indexes)

    def test_initialize_creates_model_setting_table_and_one_active_index(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "Navi" / "navi.db"
            initialize_database(database_path)

            with closing(sqlite3.connect(database_path)) as connection:
                columns = {
                    row[1]: row[2]
                    for row in connection.execute(
                        "PRAGMA table_info(model_setting)"
                    )
                }
                index_sql = connection.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' "
                    "AND name = 'idx_model_setting_one_active'"
                ).fetchone()[0]

            self.assertEqual(
                columns,
                {
                    "setting_id": "TEXT",
                    "name": "TEXT",
                    "model_provider": "TEXT",
                    "model_name": "TEXT",
                    "api_key": "TEXT",
                    "base_url": "TEXT",
                    "active": "INTEGER",
                    "created_at": "TEXT",
                    "updated_at": "TEXT",
                },
            )
            self.assertIn("WHERE active = 1", index_sql)

if __name__ == "__main__":
    unittest.main()
