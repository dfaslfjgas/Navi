"""对话列表接口，对应后端 chat_item Controller。"""

from urllib.parse import quote, urlencode

from PySide6.QtCore import QObject, Signal

from gui.api.transport import ApiTransport, response_data


def parse_chat_list(payload) -> tuple[list[dict], bool]:
    """校验并转换 GET /chats 的对话列表响应。"""
    data = response_data(payload)
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("对话列表 items 必须是数组")
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict) or raw.get("id") is None:
            raise ValueError("对话记录缺少 id")
        items.append({
            "id": str(raw["id"]),
            "name": str(raw.get("name") or "新对话"),
            "created_at": str(raw.get("created_at") or ""),
            "updated_at": str(raw.get("updated_at") or ""),
            "activity_time": str(raw.get("activity_time") or ""),
        })
    return items, bool(data.get("has_more", False))


class ChatItemApi(QObject):
    """调用对话列表的查询、创建、重命名和删除接口。"""

    chats_loaded = Signal(list, bool, bool)
    chat_created = Signal(dict)
    chat_renamed = Signal(dict)
    chat_deleted = Signal(str)

    def __init__(self, transport: ApiTransport, parent: QObject | None = None):
        super().__init__(parent)
        self.transport = transport

    def get_chat_items(
        self,
        activity_time_lt: str | None = None,
        page_size: int = 30,
    ) -> None:
        """GET /chats：获取最新对话，或加载指定活动时间之前的一页。"""
        query: dict[str, object] = {"page_size": page_size}
        is_more = activity_time_lt is not None
        if activity_time_lt:
            query["activity_time_lt"] = activity_time_lt
        path = f"/chats?{urlencode(query)}"

        def received(response) -> None:
            items, has_more = parse_chat_list(response)
            self.chats_loaded.emit(items, has_more, is_more)

        self.transport.request("chats", "GET", path, None, received)

    def create_chat_item(self, name: str | None = None) -> None:
        """POST /chats：创建对话；名称为空时由后端使用默认名称。"""
        payload = {"name": name} if name else {}
        self.transport.request(
            "create_chat",
            "POST",
            "/chats",
            payload,
            lambda response: self.chat_created.emit(response_data(response)),
        )

    def rename_chat_item(self, chat_id: str, name: str) -> None:
        """PATCH /chats/{chat_id}：修改对话名称，不改变活动时间。"""
        path = f"/chats/{quote(chat_id, safe='')}"
        self.transport.request(
            "rename_chat",
            "PATCH",
            path,
            {"name": name},
            lambda response: self.chat_renamed.emit(response_data(response)),
        )

    def delete_chat_item(self, chat_id: str) -> None:
        """DELETE /chats/{chat_id}：删除对话及后端级联的聊天内容。"""
        path = f"/chats/{quote(chat_id, safe='')}"
        self.transport.request(
            "delete_chat",
            "DELETE",
            path,
            None,
            lambda _response: self.chat_deleted.emit(chat_id),
        )
