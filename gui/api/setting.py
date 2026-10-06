"""模型设置接口，对应后端 setting Controller。"""

from urllib.parse import quote

from PySide6.QtCore import QObject, Signal

from gui.api.transport import ApiTransport, response_data


def parse_settings(payload) -> list[dict]:
    """校验并转换 GET /setting/get_setting 的配置摘要列表。"""
    if not isinstance(payload, dict) or payload.get("result") is not True:
        raise ValueError("响应缺少成功标记")
    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raise ValueError("模型配置 data 必须是数组")

    items = []
    for raw in raw_items:
        if not isinstance(raw, dict) or raw.get("setting_id") is None:
            raise ValueError("模型配置缺少 setting_id")
        items.append({
            "setting_id": str(raw["setting_id"]),
            "name": str(raw.get("name") or ""),
            "active": bool(raw.get("active", False)),
        })
    return items


def parse_setting_detail(payload) -> dict:
    """校验并转换按 ID 获取的完整模型配置。"""
    raw = response_data(payload)
    if raw.get("setting_id") is None:
        raise ValueError("模型配置缺少 setting_id")
    return {
        "setting_id": str(raw["setting_id"]),
        "name": str(raw.get("name") or ""),
        "model_provider": str(raw.get("model_provider") or "openai"),
        "model_name": str(raw.get("model_name") or ""),
        "api_key": str(raw.get("api_key") or ""),
        "base_url": str(raw.get("base_url") or ""),
        "active": bool(raw.get("active", False)),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


class SettingApi(QObject):
    """调用模型配置的创建、查询、修改和删除接口。"""

    settings_loaded = Signal(list)
    setting_loaded = Signal(dict)
    setting_tested = Signal(dict)
    setting_created = Signal(dict)
    setting_updated = Signal(dict)
    setting_deleted = Signal(str)

    def __init__(self, transport: ApiTransport, parent: QObject | None = None):
        super().__init__(parent)
        self.transport = transport

    def create_setting(
        self,
        name: str,
        model_provider: str,
        model_name: str,
        api_key: str,
        base_url: str,
        active: bool,
    ) -> None:
        """POST /setting/create_setting：新增一套模型调用配置。"""
        self.transport.request(
            "create_setting",
            "POST",
            "/setting/create_setting",
            {
                "name": name,
                "model_provider": model_provider,
                "model_name": model_name,
                "api_key": api_key,
                "base_url": base_url,
                "active": active,
            },
            lambda response: self.setting_created.emit(response_data(response)),
        )

    def get_settings(self) -> None:
        """GET /setting/get_setting：获取配置 ID、名称和激活状态。"""
        self.transport.request(
            "get_settings",
            "GET",
            "/setting/get_setting",
            None,
            lambda response: self.settings_loaded.emit(parse_settings(response)),
        )

    def get_setting(self, setting_id: str) -> None:
        """GET /setting/get_setting/setting_id/{id}：获取完整配置。"""
        path = f"/setting/get_setting/setting_id/{quote(setting_id, safe='')}"
        self.transport.request(
            "get_setting",
            "GET",
            path,
            None,
            lambda response: self.setting_loaded.emit(
                parse_setting_detail(response)
            ),
        )

    def test_setting(self) -> None:
        """POST /setting/test_setting：测试服务端当前激活配置。"""
        self.transport.request(
            "test_setting",
            "POST",
            "/setting/test_setting",
            None,
            lambda response: self.setting_tested.emit(response_data(response)),
            timeout_ms=25000,
        )

    def update_setting(
        self,
        setting_id: str,
        **changes,
    ) -> None:
        """PATCH /setting/update_setting/setting_id/{id}：部分修改配置。"""
        allowed = {
            "name",
            "model_provider",
            "model_name",
            "api_key",
            "base_url",
            "active",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"不支持的配置字段：{', '.join(sorted(unexpected))}")
        if not changes:
            raise ValueError("至少需要提供一个要修改的字段")
        path = (
            "/setting/update_setting/setting_id/"
            f"{quote(setting_id, safe='')}"
        )
        self.transport.request(
            "update_setting",
            "PATCH",
            path,
            changes,
            lambda response: self.setting_updated.emit(response_data(response)),
        )

    def delete_setting(self, setting_id: str) -> None:
        """DELETE /setting/delete_setting/setting_id/{id}：删除指定配置。"""
        path = (
            "/setting/delete_setting/setting_id/"
            f"{quote(setting_id, safe='')}"
        )
        self.transport.request(
            "delete_setting",
            "DELETE",
            path,
            None,
            lambda _response: self.setting_deleted.emit(setting_id),
        )
