"""HTTP and SSE transport used by the Navi GUI process."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlencode
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def _response_data(payload) -> dict:
    if not isinstance(payload, dict) or payload.get("result") is not True:
        raise ValueError("响应缺少成功标记")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("响应 data 必须是对象")
    return data


def parse_chat_list(payload) -> tuple[list[dict], bool]:
    data = _response_data(payload)
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


def parse_messages(payload) -> tuple[list[dict], bool]:
    data = _response_data(payload)
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


@dataclass
class _StreamState:
    run_id: str
    chat_id: str
    reply: QNetworkReply | None = None
    buffer: bytes = b""
    last_event_id: str | None = None
    retries: int = 0
    terminal: bool = False


class NaviApi(QObject):
    """All API paths and wire-format handling live in this class."""

    chats_loaded = Signal(list, bool, bool)
    messages_loaded = Signal(str, list, bool, bool)
    chat_created = Signal(dict)
    chat_renamed = Signal(dict)
    chat_deleted = Signal(str)
    message_accepted = Signal(str, str, dict)
    stream_started = Signal(str, str)
    stream_delta = Signal(str, str, str)
    stream_completed = Signal(str, dict)
    stream_failed = Signal(str, str, str)
    request_failed = Signal(str, str)

    def __init__(self, base_url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.network = QNetworkAccessManager(self)
        self._streams: dict[str, _StreamState] = {}

    def _request(
        self,
        operation: str,
        method: str,
        path: str,
        payload: dict | None,
        on_success: Callable[[dict], None],
    ) -> None:
        request = QNetworkRequest(QUrl(self.base_url + path))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setTransferTimeout(5000)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
        if method == "GET":
            reply = self.network.get(request)
        elif method == "POST":
            reply = self.network.post(request, body)
        else:
            reply = self.network.sendCustomRequest(request, method.encode("ascii"), body)

        def finished() -> None:
            raw = bytes(reply.readAll())
            try:
                response = json.loads(raw.decode("utf-8")) if raw.strip() else {}
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                if reply.error() != QNetworkReply.NetworkError.NoError or (
                    status is not None and int(status) >= 400
                ):
                    self.request_failed.emit(operation, self._error_message(response, status, reply.errorString()))
                    return
                on_success(response)
            except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
                self.request_failed.emit(operation, f"服务器响应格式错误：{error}")
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    @staticmethod
    def _error_message(payload, status, fallback: str) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                if code and message:
                    return f"{code}: {message}"
                if message:
                    return str(message)
        return fallback or f"HTTP {status}"

    def get_chats(
        self, activity_time_lt: str | None = None, page_size: int = 30
    ) -> None:
        query: dict[str, object] = {"page_size": page_size}
        is_more = activity_time_lt is not None
        if activity_time_lt:
            query["activity_time_lt"] = activity_time_lt
        path = f"/chats?{urlencode(query)}"

        def received(response) -> None:
            items, has_more = parse_chat_list(response)
            self.chats_loaded.emit(items, has_more, is_more)

        self._request("chats", "GET", path, None, received)

    def create_chat(self, name: str | None = None) -> None:
        payload = {"name": name} if name else {}
        self._request(
            "create_chat", "POST", "/chats", payload,
            lambda response: self.chat_created.emit(_response_data(response)),
        )

    def rename_chat(self, chat_id: str, name: str) -> None:
        path = f"/chats/{quote(chat_id, safe='')}"
        self._request(
            "rename_chat", "PATCH", path, {"name": name},
            lambda response: self.chat_renamed.emit(_response_data(response)),
        )

    def delete_chat(self, chat_id: str) -> None:
        path = f"/chats/{quote(chat_id, safe='')}"
        self._request(
            "delete_chat", "DELETE", path, None,
            lambda _response: self.chat_deleted.emit(chat_id),
        )

    def get_messages(
        self,
        chat_id: str,
        created_time_lt: str | None = None,
        page_size: int = 30,
    ) -> None:
        query: dict[str, object] = {"page_size": page_size}
        is_older = created_time_lt is not None
        if created_time_lt:
            query["created_time_lt"] = created_time_lt
        path = f"/chats/{quote(chat_id, safe='')}/messages?{urlencode(query)}"

        def received(response) -> None:
            messages, has_more = parse_messages(response)
            self.messages_loaded.emit(chat_id, messages, has_more, is_older)

        self._request("messages", "GET", path, None, received)

    def send_message(
        self, chat_id: str, content: str, client_message_id: str | None = None
    ) -> str:
        message_key = client_message_id or str(uuid4())
        path = f"/chats/{quote(chat_id, safe='')}/messages"
        payload = {"content": content, "client_message_id": message_key}

        def received(response) -> None:
            data = _response_data(response)
            run_id = str(data["run_id"])
            user_message = data["user_message"]
            if not isinstance(user_message, dict):
                raise ValueError("发送响应缺少 user_message")
            self.message_accepted.emit(chat_id, run_id, user_message)
            self._subscribe(run_id, chat_id)

        self._request("send_message", "POST", path, payload, received)
        return message_key

    def _subscribe(self, run_id: str, chat_id: str) -> None:
        state = self._streams.get(run_id)
        if state is None:
            state = _StreamState(run_id=run_id, chat_id=chat_id)
            self._streams[run_id] = state
        request = QNetworkRequest(QUrl(f"{self.base_url}/runs/{quote(run_id, safe='')}/events"))
        request.setRawHeader(b"Accept", b"text/event-stream")
        if state.last_event_id:
            request.setRawHeader(b"Last-Event-ID", state.last_event_id.encode("ascii"))
        reply = self.network.get(request)
        state.reply = reply
        reply.readyRead.connect(lambda: self._read_stream(state))
        reply.finished.connect(lambda: self._stream_finished(state))

    def _read_stream(self, state: _StreamState) -> None:
        if state.reply is None:
            return
        state.buffer += bytes(state.reply.readAll()).replace(b"\r\n", b"\n")
        while b"\n\n" in state.buffer:
            block, state.buffer = state.buffer.split(b"\n\n", 1)
            if block:
                self._dispatch_event(state, block)

    def _dispatch_event(self, state: _StreamState, block: bytes) -> None:
        event_name = "message"
        event_id = None
        data_lines = []
        try:
            for raw_line in block.decode("utf-8").splitlines():
                if not raw_line or raw_line.startswith(":"):
                    continue
                field, _, value = raw_line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "event":
                    event_name = value
                elif field == "id":
                    event_id = value
                elif field == "data":
                    data_lines.append(value)
            if event_id:
                state.last_event_id = event_id
            if not data_lines:
                return
            data = json.loads("\n".join(data_lines))
            if event_name == "started":
                self.stream_started.emit(state.run_id, str(data["assistant_message_id"]))
            elif event_name == "delta":
                self.stream_delta.emit(
                    state.run_id, str(data["assistant_message_id"]), str(data["delta"])
                )
            elif event_name == "completed":
                message = data.get("message")
                if not isinstance(message, dict):
                    raise ValueError("completed 事件缺少 message")
                state.terminal = True
                self.stream_completed.emit(state.run_id, message)
            elif event_name == "error":
                state.terminal = True
                self.stream_failed.emit(
                    state.run_id,
                    str(data.get("code") or "STREAM_ERROR"),
                    str(data.get("message") or "Agent 运行失败"),
                )
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            state.terminal = True
            self.stream_failed.emit(state.run_id, "INVALID_SSE_EVENT", str(error))

    def _stream_finished(self, state: _StreamState) -> None:
        reply = state.reply
        if reply is None:
            return
        self._read_stream(state)
        if state.buffer.strip() and not state.terminal:
            self._dispatch_event(state, state.buffer.strip())
            state.buffer = b""
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        detail = reply.errorString()
        reply.deleteLater()
        state.reply = None
        if state.terminal:
            self._streams.pop(state.run_id, None)
            return
        if status is not None and int(status) >= 400:
            state.terminal = True
            self._streams.pop(state.run_id, None)
            self.stream_failed.emit(state.run_id, f"HTTP_{status}", detail or f"HTTP {status}")
            return
        if state.retries < 3:
            state.retries += 1
            QTimer.singleShot(250 * state.retries, lambda: self._subscribe(state.run_id, state.chat_id))
            return
        state.terminal = True
        self._streams.pop(state.run_id, None)
        self.stream_failed.emit(state.run_id, "STREAM_DISCONNECTED", detail or "SSE 连接已断开")
