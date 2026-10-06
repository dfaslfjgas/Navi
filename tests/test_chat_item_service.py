"""创建对话的 Service 与 DAO 测试。"""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.database import initialize_database
from server.service.chat_item import (
    create_chat_item,
    delete_chat_item,
    get_chat_items,
    rename_chat_item,
)


class ChatItemServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "Navi" / "navi.db"
        )
        initialize_database(self.database_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_create_chat_item_inserts_trimmed_name(self):
        created = create_chat_item(
            "  数据库设计  ",
            database_path=self.database_path,
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT id, name, created_at, updated_at, activity_time "
                "FROM chat_item WHERE id = ?",
                (created["id"],),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row, tuple(created.values()))
        self.assertTrue(created["id"].startswith("chat_"))
        self.assertEqual(created["name"], "数据库设计")

    def test_none_name_uses_default_name(self):
        created = create_chat_item(None, database_path=self.database_path)
        self.assertEqual(created["name"], "新对话")

    def test_blank_name_is_rejected_without_inserting(self):
        with self.assertRaisesRegex(ValueError, "对话名称不能为空"):
            create_chat_item("   ", database_path=self.database_path)

        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM chat_item"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_rename_updates_name_and_updated_at_only(self):
        created = create_chat_item("原名称", database_path=self.database_path)
        renamed_time = "2026-10-06T08:30:00.123456Z"

        with patch(
            "server.service.chat_item.utc_now",
            return_value=renamed_time,
        ):
            renamed = rename_chat_item(
                created["id"],
                "  新名称  ",
                database_path=self.database_path,
            )

        self.assertEqual(renamed["name"], "新名称")
        self.assertEqual(renamed["updated_at"], renamed_time)
        self.assertEqual(renamed["created_at"], created["created_at"])
        self.assertEqual(renamed["activity_time"], created["activity_time"])

    def test_rename_rejects_blank_name_before_updating(self):
        created = create_chat_item("原名称", database_path=self.database_path)

        with self.assertRaisesRegex(ValueError, "对话名称不能为空"):
            rename_chat_item(
                created["id"],
                "   ",
                database_path=self.database_path,
            )

        with closing(sqlite3.connect(self.database_path)) as connection:
            stored = connection.execute(
                "SELECT name, updated_at FROM chat_item WHERE id = ?",
                (created["id"],),
            ).fetchone()
        self.assertEqual(stored, ("原名称", created["updated_at"]))

    def test_rename_missing_chat_raises_lookup_error(self):
        with self.assertRaisesRegex(LookupError, "对话不存在"):
            rename_chat_item(
                "chat_missing",
                "新名称",
                database_path=self.database_path,
            )

    def test_get_chat_items_uses_time_pagination(self):
        created = []
        for index in range(3):
            timestamp = f"2026-10-06T08:30:0{index}.000000Z"
            with patch(
                "server.service.chat_item.utc_now",
                return_value=timestamp,
            ):
                created.append(
                    create_chat_item(
                        f"对话 {index}",
                        database_path=self.database_path,
                    )
                )

        first_page = get_chat_items(
            page_size=2,
            database_path=self.database_path,
        )
        self.assertTrue(first_page["has_more"])
        self.assertEqual(
            [item["id"] for item in first_page["items"]],
            [created[2]["id"], created[1]["id"]],
        )

        second_page = get_chat_items(
            first_page["items"][-1]["activity_time"],
            page_size=2,
            database_path=self.database_path,
        )
        self.assertFalse(second_page["has_more"])
        self.assertEqual(
            [item["id"] for item in second_page["items"]],
            [created[0]["id"]],
        )

    def test_delete_chat_item_removes_record(self):
        created = create_chat_item("待删除", database_path=self.database_path)

        deleted = delete_chat_item(
            created["id"],
            database_path=self.database_path,
        )

        self.assertEqual(deleted, {"id": created["id"]})
        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM chat_item WHERE id = ?",
                (created["id"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_delete_missing_chat_raises_lookup_error(self):
        with self.assertRaisesRegex(LookupError, "对话不存在"):
            delete_chat_item(
                "chat_missing",
                database_path=self.database_path,
            )


if __name__ == "__main__":
    unittest.main()
