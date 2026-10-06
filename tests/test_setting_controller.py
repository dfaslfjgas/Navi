"""模型配置 Controller 的 HTTP 与数据库行为测试。"""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.main import create_app
from server.model_runtime import get_active_model_setting


class SettingControllerTests(unittest.TestCase):
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

    def create_setting(
        self,
        name: str,
        *,
        active: bool,
        model_name: str = "gpt-test",
    ) -> dict:
        response = self.client.post(
            "/api/v1/setting/create_setting",
            json={
                "name": name,
                "model_provider": "openai",
                "model_name": model_name,
                "api_key": f"key-{name}",
                "base_url": "http://127.0.0.1:11434/v1/",
                "active": active,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["data"]

    def test_list_returns_summaries_and_detail_returns_complete_information(self):
        created = self.create_setting("本地模型", active=True)

        response = self.client.get("/api/v1/setting/get_setting")

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]
        self.assertEqual(
            items,
            [{
                "setting_id": created["setting_id"],
                "name": "本地模型",
                "active": True,
            }],
        )

        response = self.client.get(
            "/api/v1/setting/get_setting/setting_id/"
            f"{created['setting_id']}"
        )
        self.assertEqual(response.status_code, 200)
        detail = response.json()["data"]
        self.assertEqual(detail, created)
        self.assertEqual(detail["model_provider"], "openai")
        self.assertEqual(detail["api_key"], "key-本地模型")
        self.assertEqual(
            detail["base_url"],
            "http://127.0.0.1:11434/v1",
        )
        self.assertTrue(detail["active"])

    def test_get_missing_setting_detail_returns_not_found(self):
        response = self.client.get(
            "/api/v1/setting/get_setting/setting_id/setting_missing"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SETTING_NOT_FOUND")

    def test_test_setting_invokes_openai_compatible_model(self):
        created = self.create_setting("待测试", active=True)

        class FakeModel:
            async def ainvoke(self, prompt):
                self.prompt = prompt
                return type("Message", (), {"content": "OK"})()

        fake_model = FakeModel()
        with patch(
            "server.service.setting._init_chat_model",
            return_value=fake_model,
        ) as initialize_model:
            response = self.client.post(
                "/api/v1/setting/test_setting"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "setting_id": created["setting_id"],
                "success": True,
                "reply": "OK",
            },
        )
        initialize_model.assert_called_once_with(
            model="gpt-test",
            model_provider="openai",
            api_key="key-待测试",
            base_url="http://127.0.0.1:11434/v1",
            temperature=0,
            timeout=15,
            max_retries=0,
        )
        self.assertIn("连接测试", fake_model.prompt)

    def test_test_setting_returns_bad_gateway_when_model_call_fails(self):
        self.create_setting("错误配置", active=True)

        class FailingModel:
            async def ainvoke(self, _prompt):
                raise RuntimeError("unauthorized")

        with patch(
            "server.service.setting._init_chat_model",
            return_value=FailingModel(),
        ):
            response = self.client.post(
                "/api/v1/setting/test_setting"
            )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["result"])
        self.assertEqual(
            response.json()["error"]["code"],
            "MODEL_CONNECTION_FAILED",
        )

    def test_test_setting_requires_an_active_configuration(self):
        response = self.client.post("/api/v1/setting/test_setting")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SETTING_NOT_FOUND")
        self.assertIn("没有激活", response.json()["error"]["message"])

    def test_test_setting_rejects_incomplete_runtime_configuration(self):
        incomplete_setting = {
            "setting_id": "setting_incomplete",
            "model_provider": "openai",
            "model_name": "",
            "api_key": "key-test",
            "base_url": "https://example.com/v1",
        }
        with patch(
            "server.service.setting.get_active_model_setting",
            return_value=incomplete_setting,
        ), patch("server.service.setting._init_chat_model") as initialize_model:
            response = self.client.post("/api/v1/setting/test_setting")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
        self.assertIn("模型名称", response.json()["error"]["message"])
        initialize_model.assert_not_called()

    def test_deactivating_current_setting_clears_runtime_configuration(self):
        created = self.create_setting("可取消配置", active=True)

        response = self.client.patch(
            "/api/v1/setting/update_setting/setting_id/"
            f"{created['setting_id']}",
            json={"active": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["active"])
        self.assertIsNone(get_active_model_setting())
        test_response = self.client.post("/api/v1/setting/test_setting")
        self.assertEqual(test_response.status_code, 404)
        self.assertEqual(
            test_response.json()["error"]["code"],
            "SETTING_NOT_FOUND",
        )

    def test_get_settings_returns_documented_error_on_database_failure(self):
        with patch(
            "server.controller.setting.get_settings_service",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            response = self.client.get("/api/v1/setting/get_setting")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "result": False,
                "data": None,
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "模型配置读取或保存失败",
                },
            },
        )

    def test_new_active_setting_deactivates_previous_setting(self):
        first = self.create_setting("配置一", active=True)
        second = self.create_setting("配置二", active=True)

        first_record = self.client.get(
            "/api/v1/setting/get_setting/setting_id/"
            f"{first['setting_id']}"
        ).json()["data"]
        second_record = self.client.get(
            "/api/v1/setting/get_setting/setting_id/"
            f"{second['setting_id']}"
        ).json()["data"]
        self.assertFalse(first_record["active"])
        self.assertTrue(second_record["active"])
        self.assertEqual(
            get_active_model_setting()["setting_id"],
            second["setting_id"],
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM model_setting WHERE active = 1"
            ).fetchone()[0]
        self.assertEqual(active_count, 1)

    def test_update_setting_changes_only_provided_fields_and_can_activate(self):
        first = self.create_setting("配置一", active=True)
        second = self.create_setting("配置二", active=False)

        before_activation = self.client.get(
            "/api/v1/setting/get_setting"
        ).json()["data"]
        self.assertEqual(
            [item["setting_id"] for item in before_activation],
            [second["setting_id"], first["setting_id"]],
        )

        response = self.client.patch(
            "/api/v1/setting/update_setting/setting_id/"
            f"{second['setting_id']}",
            json={
                "model_provider": "anthropic",
                "model_name": "new-model",
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()["data"]
        self.assertEqual(updated["name"], second["name"])
        self.assertEqual(updated["api_key"], second["api_key"])
        self.assertEqual(updated["model_name"], "new-model")
        self.assertEqual(updated["model_provider"], "anthropic")
        self.assertTrue(updated["active"])

        previous = self.client.get(
            "/api/v1/setting/get_setting/setting_id/"
            f"{first['setting_id']}"
        ).json()["data"]
        self.assertFalse(previous["active"])

        after_activation = self.client.get(
            "/api/v1/setting/get_setting"
        ).json()["data"]
        self.assertEqual(
            [item["setting_id"] for item in after_activation],
            [second["setting_id"], first["setting_id"]],
        )

    def test_update_requires_at_least_one_value(self):
        created = self.create_setting("待修改", active=False)

        response = self.client.patch(
            "/api/v1/setting/update_setting/setting_id/"
            f"{created['setting_id']}",
            json={},
        )

        self.assertEqual(response.status_code, 422)

    def test_duplicate_name_returns_invalid_request(self):
        self.create_setting("重复名称", active=False)

        response = self.client.post(
            "/api/v1/setting/create_setting",
            json={
                "name": "重复名称",
                "model_provider": "openai",
                "model_name": "another-model",
                "api_key": "another-key",
                "base_url": "https://example.com/v1",
                "active": False,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(
            response.json()["error"]["message"],
            "配置名称已存在",
        )

    def test_invalid_model_provider_is_rejected_before_insert(self):
        response = self.client.post(
            "/api/v1/setting/create_setting",
            json={
                "name": "拼写错误",
                "model_provider": "opneai",
                "model_name": "model-a",
                "api_key": "key-a",
                "base_url": "https://example.com/v1",
                "active": False,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
        self.assertIn(
            "不支持的 Model Provider",
            response.json()["error"]["message"],
        )

    def test_delete_setting_by_id_and_missing_returns_not_found(self):
        created = self.create_setting("待删除", active=False)
        path = (
            "/api/v1/setting/delete_setting/setting_id/"
            f"{created['setting_id']}"
        )

        response = self.client.delete(path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {"setting_id": created["setting_id"]},
        )
        self.assertEqual(self.client.delete(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
