"""聊天内容接口，对应后端 chat_content Controller。"""

from urllib.parse import quote, urlencode

from PySide6.QtCore import QObject, Signal

from gui.api.transport import ApiTransport, response_data


def parse_messages(payload) -> tuple[list[dict], bool]:
    """校验并转换 GET /chat_content/{chat_id}/messages 的响应。"""
    data = response_data(payload)
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("消息列表 items 必须是数组")
    messages = []
    for raw in raw_items:
        if not isinstance(raw, dict) or raw.get("id") is None:
            raise ValueError("消息记录缺少 id")
        role = str(raw.get("role") or "")
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"不支持的消息角色：{role}")
        messages.append({
            "id": str(raw["id"]),
            "role": role,
            "content": str(raw.get("content") or ""),
            "status": str(raw.get("status") or "completed"),
            "created_time": str(raw.get("created_time") or ""),
        })
    return messages, bool(data.get("has_more", False))


class ChatContentApi(QObject):
    """调用聊天消息的分页读取和直接新增接口。"""

    messages_loaded = Signal(str, list, bool, bool)
    content_added = Signal(str, dict)

    def __init__(self, transport: ApiTransport, parent: QObject | None = None):
        super().__init__(parent)
        self.transport = transport

    def get_chat_content(
        self,
        chat_id: str,
        created_time_lt: str | None = None,
        page_size: int = 30,
    ) -> None:
        """GET /chat_content/{chat_id}/messages：获取最新或更早的消息。"""
        query: dict[str, object] = {"page_size": page_size}
        is_older = created_time_lt is not None
        if created_time_lt:
            query["created_time_lt"] = created_time_lt
        path = (
            f"/chat_content/{quote(chat_id, safe='')}/messages?"
            f"{urlencode(query)}"
        )

        def received(response) -> None:
            messages, has_more = parse_messages(response)
            self.messages_loaded.emit(chat_id, messages, has_more, is_older)

        self.transport.request("messages", "GET", path, None, received)

    def add_chat_content(self, chat_id: str, role: str, content: str) -> None:
        """POST /chat_content/{chat_id}/messages：直接保存一条聊天消息。"""
        path = f"/chat_content/{quote(chat_id, safe='')}/messages"
        payload = {"role": role, "content": content}
        self.transport.request(
            "add_chat_content",
            "POST",
            path,
            payload,
            lambda response: self.content_added.emit(
                chat_id,
                response_data(response),
            ),
        )
