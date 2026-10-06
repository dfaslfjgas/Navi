"""创建对话 Controller 的 HTTP 行为测试。"""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.main import create_app


class ChatItemControllerTests(unittest.TestCase):
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

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.environment.stop()
        self.temporary_directory.cleanup()

    def test_create_chat_item_calls_service_and_persists_result(self):
        response = self.client.post(
            "/api/v1/chats",
            json={"name": "  新的数据库对话  "},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["result"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["name"], "新的数据库对话")

        with closing(sqlite3.connect(self.database_path)) as connection:
            stored_name = connection.execute(
                "SELECT name FROM chat_item WHERE id = ?",
                (body["data"]["id"],),
            ).fetchone()[0]
        self.assertEqual(stored_name, "新的数据库对话")

    def test_blank_name_returns_documented_error(self):
        response = self.client.post("/api/v1/chats", json={"name": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "result": False,
                "data": None,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "对话名称不能为空",
                },
            },
        )

    def test_rename_chat_item_updates_name_without_changing_activity_time(self):
        created = self.client.post(
            "/api/v1/chats",
            json={"name": "原名称"},
        ).json()["data"]

        response = self.client.patch(
            f"/api/v1/chats/{created['id']}",
            json={"name": "  新名称  "},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["result"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["name"], "新名称")
        self.assertEqual(
            body["data"]["activity_time"],
            created["activity_time"],
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            stored = connection.execute(
                "SELECT name, activity_time FROM chat_item WHERE id = ?",
                (created["id"],),
            ).fetchone()
        self.assertEqual(stored, ("新名称", created["activity_time"]))

    def test_rename_blank_name_returns_invalid_request(self):
        created = self.client.post(
            "/api/v1/chats",
            json={"name": "原名称"},
        ).json()["data"]

        response = self.client.patch(
            f"/api/v1/chats/{created['id']}",
            json={"name": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_rename_missing_chat_returns_not_found(self):
        response = self.client.patch(
            "/api/v1/chats/chat_missing",
            json={"name": "新名称"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "result": False,
                "data": None,
                "error": {
                    "code": "CHAT_NOT_FOUND",
                    "message": "对话不存在",
                },
            },
        )

    def test_get_chat_items_reads_query_parameters_from_url(self):
        first = self.client.post(
            "/api/v1/chats",
            json={"name": "第一条"},
        ).json()["data"]
        second = self.client.post(
            "/api/v1/chats",
            json={"name": "第二条"},
        ).json()["data"]

        response = self.client.get("/api/v1/chats?page_size=1")

        self.assertEqual(response.status_code, 200)
        first_page = response.json()["data"]
        self.assertTrue(first_page["has_more"])
        self.assertEqual(first_page["items"][0]["id"], second["id"])

        cursor = first_page["items"][0]["activity_time"]
        response = self.client.get(
            "/api/v1/chats",
            params={"activity_time_lt": cursor, "page_size": 1},
        )
        second_page = response.json()["data"]
        self.assertFalse(second_page["has_more"])
        self.assertEqual(second_page["items"][0]["id"], first["id"])

    def test_delete_chat_item_uses_chat_id_from_url(self):
        created = self.client.post(
            "/api/v1/chats",
            json={"name": "待删除"},
        ).json()["data"]

        response = self.client.delete(f"/api/v1/chats/{created['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"result": True, "data": {"id": created["id"]}, "error": None},
        )

        missing = self.client.delete(f"/api/v1/chats/{created['id']}")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "CHAT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
