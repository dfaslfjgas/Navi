"""Agent 消息提交与 SSE 流式回复接口。"""

import json
from dataclasses import dataclass
from urllib.parse import quote
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from gui.api.transport import ApiTransport, response_data


@dataclass
class _StreamState:
    run_id: str
    chat_id: str
    reply: QNetworkReply | None = None
    buffer: bytes = b""
    last_event_id: str | None = None
    retries: int = 0
    terminal: bool = False


class AgentApi(QObject):
    """提交 Agent 任务，并把 SSE 事件转换成 Qt 信号。"""

    message_accepted = Signal(str, str, dict)
    stream_started = Signal(str, str)
    stream_delta = Signal(str, str, str)
    stream_completed = Signal(str, dict)
    stream_failed = Signal(str, str, str)

    def __init__(self, transport: ApiTransport, parent: QObject | None = None):
        super().__init__(parent)
        self.transport = transport
        self._streams: dict[str, _StreamState] = {}

    def send_message(
        self,
        chat_id: str,
        content: str,
        client_message_id: str | None = None,
    ) -> str:
        """POST /chats/{chat_id}/messages：提交消息并创建 Agent run。"""
        message_key = client_message_id or str(uuid4())
        path = f"/chats/{quote(chat_id, safe='')}/messages"
        payload = {
            "content": content,
            "client_message_id": message_key,
        }

        def received(response) -> None:
            data = response_data(response)
            run_id = str(data["run_id"])
            user_message = data["user_message"]
            if not isinstance(user_message, dict):
                raise ValueError("发送响应缺少 user_message")
            self.message_accepted.emit(chat_id, run_id, user_message)
            self._subscribe(run_id, chat_id)

        self.transport.request(
            "send_message",
            "POST",
            path,
            payload,
            received,
        )
        return message_key

    def _subscribe(self, run_id: str, chat_id: str) -> None:
        """GET /runs/{run_id}/events：连接或重连 Agent SSE 事件流。"""
        state = self._streams.get(run_id)
        if state is None:
            state = _StreamState(run_id=run_id, chat_id=chat_id)
            self._streams[run_id] = state
        request = QNetworkRequest(
            QUrl(
                f"{self.transport.base_url}/runs/"
                f"{quote(run_id, safe='')}/events"
            )
        )
        request.setRawHeader(b"Accept", b"text/event-stream")
        if state.last_event_id:
            request.setRawHeader(
                b"Last-Event-ID",
                state.last_event_id.encode("ascii"),
            )
        reply = self.transport.network.get(request)
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
        """解析单个 SSE 事件并发出对应的 Qt 信号。"""
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
                self.stream_started.emit(
                    state.run_id,
                    str(data["assistant_message_id"]),
                )
            elif event_name == "delta":
                self.stream_delta.emit(
                    state.run_id,
                    str(data["assistant_message_id"]),
                    str(data["delta"]),
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
        except (
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            state.terminal = True
            self.stream_failed.emit(
                state.run_id,
                "INVALID_SSE_EVENT",
                str(error),
            )

    def _stream_finished(self, state: _StreamState) -> None:
        """处理 SSE 结束、错误和最多三次断线重连。"""
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
            self.stream_failed.emit(
                state.run_id,
                f"HTTP_{status}",
                detail or f"HTTP {status}",
            )
            return
        if state.retries < 3:
            state.retries += 1
            QTimer.singleShot(
                250 * state.retries,
                lambda: self._subscribe(state.run_id, state.chat_id),
            )
            return
        state.terminal = True
        self._streams.pop(state.run_id, None)
        self.stream_failed.emit(
            state.run_id,
            "STREAM_DISCONNECTED",
            detail or "SSE 连接已断开",
        )
