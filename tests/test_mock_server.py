"""Contract checks for the FastAPI in-memory server."""

import json
import unittest

try:
    from fastapi.testclient import TestClient
    from mock_server import MockStore, create_app, split_stream_text
    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False


@unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI test dependencies are not installed")
class MockServerTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_chat_and_message_time_pagination(self):
        first = self.client.get("/api/v1/chats", params={"page_size": 1})
        self.assertEqual(first.status_code, 200)
        first_data = first.json()["data"]
        self.assertEqual(len(first_data["items"]), 1)
        self.assertTrue(first_data["has_more"])
        boundary = first_data["items"][-1]["activity_time"]
        second = self.client.get(
            "/api/v1/chats",
            params={"page_size": 1, "activity_time_lt": boundary},
        ).json()["data"]
        self.assertEqual(len(second["items"]), 1)
        self.assertLess(second["items"][0]["activity_time"], boundary)

        chat_id = first_data["items"][0]["id"]
        messages = self.client.get(
            f"/api/v1/chats/{chat_id}/messages", params={"page_size": 1}
        ).json()["data"]
        self.assertEqual(len(messages["items"]), 1)
        self.assertTrue(messages["has_more"])
        oldest_time = messages["items"][0]["created_time"]
        older = self.client.get(
            f"/api/v1/chats/{chat_id}/messages",
            params={"page_size": 1, "created_time_lt": oldest_time},
        ).json()["data"]
        self.assertEqual(len(older["items"]), 1)
        self.assertLess(older["items"][0]["created_time"], oldest_time)

    def test_first_message_page_contains_latest_thirty(self):
        store = MockStore(seed=False)
        chat = store.create_chat("分页测试")
        for index in range(35):
            store.add_message(chat["id"], "user", f"消息 {index + 1}")
        page = store.list_messages(chat["id"], None, 30)
        self.assertTrue(page["has_more"])
        self.assertEqual(len(page["items"]), 30)
        self.assertEqual(page["items"][0]["content"], "消息 6")
        self.assertEqual(page["items"][-1]["content"], "消息 35")

    def test_create_rename_and_delete(self):
        created = self.client.post("/api/v1/chats", json={"name": "临时对话"})
        self.assertEqual(created.status_code, 201)
        chat = created.json()["data"]
        renamed = self.client.patch(
            f"/api/v1/chats/{chat['id']}", json={"name": "已经改名"}
        )
        self.assertEqual(renamed.json()["data"]["name"], "已经改名")
        deleted = self.client.delete(f"/api/v1/chats/{chat['id']}")
        self.assertEqual(deleted.status_code, 200)
        missing = self.client.get(f"/api/v1/chats/{chat['id']}/messages")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "CHAT_NOT_FOUND")

    def test_send_message_and_receive_sse(self):
        chat = self.client.post("/api/v1/chats", json={}).json()["data"]
        sent = self.client.post(
            f"/api/v1/chats/{chat['id']}/messages",
            json={"content": "测试流", "client_message_id": "client-1"},
        )
        self.assertEqual(sent.status_code, 202)
        run_id = sent.json()["data"]["run_id"]
        with self.client.stream("GET", f"/api/v1/runs/{run_id}/events") as response:
            self.assertEqual(response.status_code, 200)
            body = "\n".join(response.iter_lines())
        self.assertIn("event: started", body)
        self.assertIn("event: delta", body)
        self.assertIn("event: completed", body)
        delta_data = [
            json.loads(line.removeprefix("data: "))["delta"]
            for line in body.splitlines()
            if line.startswith("data: ") and '"delta"' in line
        ]
        self.assertGreater(len(delta_data), 3)
        completed_data = next(
            line.removeprefix("data: ")
            for line in body.splitlines()
            if line.startswith("data: ") and '"finish_reason"' in line
        )
        completed = json.loads(completed_data)
        self.assertEqual(completed["finish_reason"], "stop")
        self.assertEqual("".join(delta_data), completed["message"]["content"])

    def test_stream_text_is_split_without_changing_content(self):
        text = "这是一段用于模拟流式输出的内容。"
        chunks = split_stream_text(text)
        self.assertGreater(len(chunks), 3)
        self.assertEqual("".join(chunks), text)

    def test_idempotency_conflict(self):
        chat = self.client.post("/api/v1/chats", json={}).json()["data"]
        request = {"content": "你好", "client_message_id": "same-id"}
        first = self.client.post(f"/api/v1/chats/{chat['id']}/messages", json=request)
        duplicate = self.client.post(f"/api/v1/chats/{chat['id']}/messages", json=request)
        self.assertEqual(first.json()["data"]["run_id"], duplicate.json()["data"]["run_id"])
        conflict = self.client.post(
            f"/api/v1/chats/{chat['id']}/messages",
            json={"content": "不同内容", "client_message_id": "same-id"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
