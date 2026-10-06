"""聊天内容 Controller 的 HTTP 行为测试。"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.main import create_app


class ChatContentControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "Navi" / "navi.db"
        )
        self.environment = patch.dict(
            os.environ,
            {"NAVI_DATABASE_PATH": str(self.database_path)},
        )
        self.environment.start()
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()
        self.chat = self.client.post(
            "/api/v1/chats",
            json={"name": "消息接口测试"},
        ).json()["data"]

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.environment.stop()
        self.temporary_directory.cleanup()

    def test_add_and_get_chat_content(self):
        created = self.client.post(
            f"/api/v1/chat_content/{self.chat['id']}/messages",
            json={"role": "user", "content": "第一条消息"},
        )

        self.assertEqual(created.status_code, 201)
        created_body = created.json()
        self.assertTrue(created_body["result"])
        self.assertEqual(created_body["data"]["role"], "user")
        self.assertEqual(created_body["data"]["content"], "第一条消息")

        response = self.client.get(
            f"/api/v1/chat_content/{self.chat['id']}/messages?page_size=30"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["result"])
        self.assertFalse(body["data"]["has_more"])
        self.assertEqual(body["data"]["items"], [created_body["data"]])

    def test_missing_chat_returns_not_found(self):
        created = self.client.post(
            "/api/v1/chat_content/chat_missing/messages",
            json={"role": "user", "content": "消息"},
        )
        loaded = self.client.get("/api/v1/chat_content/chat_missing/messages")

        self.assertEqual(created.status_code, 404)
        self.assertEqual(loaded.status_code, 404)
        self.assertEqual(created.json()["error"]["code"], "CHAT_NOT_FOUND")
        self.assertEqual(loaded.json()["error"]["code"], "CHAT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
