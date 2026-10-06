"""聊天内容 Service 与 DAO 测试。"""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.database import initialize_database
from server.service.chat_content import add_chat_content, get_chat_content
from server.service.chat_item import create_chat_item, delete_chat_item


class ChatContentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "Navi" / "navi.db"
        )
        initialize_database(self.database_path)
        self.chat = create_chat_item(
            "消息测试",
            database_path=self.database_path,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_add_message_persists_content_and_updates_activity_time(self):
        created_time = "2026-10-06T09:00:00.123456Z"
        with patch(
            "server.service.chat_content.utc_now",
            return_value=created_time,
        ):
            message = add_chat_content(
                self.chat["id"],
                "user",
                "你好，Navi",
                database_path=self.database_path,
            )

        self.assertEqual(message["role"], "user")
        self.assertEqual(message["content"], "你好，Navi")
        self.assertEqual(message["status"], "completed")
        self.assertEqual(message["created_time"], created_time)

        with closing(sqlite3.connect(self.database_path)) as connection:
            stored_message = connection.execute(
                "SELECT content_id, chat_id, role, content, status, created_time "
                "FROM chat_content WHERE content_id = ?",
                (message["id"],),
            ).fetchone()
            activity_time = connection.execute(
                "SELECT activity_time FROM chat_item WHERE id = ?",
                (self.chat["id"],),
            ).fetchone()[0]

        self.assertEqual(
            stored_message,
            (
                message["id"],
                self.chat["id"],
                "user",
                "你好，Navi",
                "completed",
                created_time,
            ),
        )
        self.assertEqual(activity_time, created_time)

    def test_get_messages_returns_latest_thirty_oldest_to_newest(self):
        messages = []
        for index in range(35):
            timestamp = f"2026-10-06T09:00:{index:02d}.000000Z"
            with patch(
                "server.service.chat_content.utc_now",
                return_value=timestamp,
            ):
                messages.append(
                    add_chat_content(
                        self.chat["id"],
                        "assistant",
                        f"消息 {index}",
                        database_path=self.database_path,
                    )
                )

        latest = get_chat_content(
            self.chat["id"],
            database_path=self.database_path,
        )
        self.assertTrue(latest["has_more"])
        self.assertEqual(len(latest["items"]), 30)
        self.assertEqual(
            [item["id"] for item in latest["items"]],
            [item["id"] for item in messages[5:]],
        )

        older = get_chat_content(
            self.chat["id"],
            latest["items"][0]["created_time"],
            database_path=self.database_path,
        )
        self.assertFalse(older["has_more"])
        self.assertEqual(
            [item["id"] for item in older["items"]],
            [item["id"] for item in messages[:5]],
        )

    def test_missing_chat_is_rejected(self):
        with self.assertRaisesRegex(LookupError, "对话不存在"):
            add_chat_content(
                "chat_missing",
                "user",
                "消息",
                database_path=self.database_path,
            )
        with self.assertRaisesRegex(LookupError, "对话不存在"):
            get_chat_content(
                "chat_missing",
                database_path=self.database_path,
            )

    def test_deleting_chat_cascades_to_messages(self):
        add_chat_content(
            self.chat["id"],
            "user",
            "将被删除",
            database_path=self.database_path,
        )

        delete_chat_item(self.chat["id"], database_path=self.database_path)

        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM chat_content WHERE chat_id = ?",
                (self.chat["id"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
