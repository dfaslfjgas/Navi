"""FastAPI-based in-memory server for developing the Navi GUI."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


def success(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"result": True, "data": data, "error": None},
    )


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ChatCreate(BaseModel):
    name: str | None = None


class ChatRename(BaseModel):
    name: str


class MessageCreate(BaseModel):
    content: str
    client_message_id: str


class MockStore:
    """All state is discarded when the server process exits."""

    def __init__(self, seed: bool = True):
        self.lock = RLock()
        self.chats: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.runs: dict[str, dict] = {}
        self.idempotency: dict[tuple[str, str], tuple[str, str, dict]] = {}
        self.active_runs: dict[str, str] = {}
        self.next_chat_id = 1
        self.next_message_id = 1
        self._last_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        if seed:
            first = self.create_chat("认识 Navi")
            self.add_message(first["id"], "user", "你好，Navi")
            self.add_message(first["id"], "assistant", "你好！这是用于开发界面的示例对话。")
            second = self.create_chat("界面功能示例")
            self.add_message(second["id"], "user", "对话记录可以怎样查看？")
            self.add_message(second["id"], "assistant", "点击左上角的小狗图标，在左侧展开对话列表。")

    def _time(self) -> str:
        now = datetime.now(timezone.utc)
        if now <= self._last_time:
            now = self._last_time + timedelta(microseconds=1)
        self._last_time = now
        return now.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def create_chat(self, name: str | None = None) -> dict:
        with self.lock:
            value = (name or "新对话").strip()
            if not value or len(value) > 100:
                raise ApiError(400, "INVALID_REQUEST", "对话名称必须为 1～100 个字符")
            chat_id = f"chat_{self.next_chat_id}"
            self.next_chat_id += 1
            now = self._time()
            chat = {
                "id": chat_id,
                "name": value,
                "created_at": now,
                "updated_at": now,
                "activity_time": now,
            }
            self.chats[chat_id] = chat
            self.messages[chat_id] = []
            return chat.copy()

    def list_chats(self, activity_time_lt: str | None, page_size: int) -> dict:
        with self.lock:
            records = sorted(
                self.chats.values(), key=lambda item: item["activity_time"], reverse=True
            )
            if activity_time_lt:
                records = [
                    item for item in records if item["activity_time"] < activity_time_lt
                ]
            page = records[:page_size]
            return {
                "items": [item.copy() for item in page],
                "has_more": len(records) > page_size,
            }

    def rename_chat(self, chat_id: str, name: str) -> dict:
        with self.lock:
            chat = self.chats.get(chat_id)
            if chat is None:
                raise ApiError(404, "CHAT_NOT_FOUND", "对话不存在")
            value = name.strip()
            if not value or len(value) > 100:
                raise ApiError(400, "INVALID_REQUEST", "对话名称必须为 1～100 个字符")
            chat["name"] = value
            chat["updated_at"] = self._time()
            return chat.copy()

    def delete_chat(self, chat_id: str) -> None:
        with self.lock:
            if chat_id not in self.chats:
                raise ApiError(404, "CHAT_NOT_FOUND", "对话不存在")
            if chat_id in self.active_runs:
                raise ApiError(409, "CHAT_BUSY", "对话正在生成回复")
            del self.chats[chat_id]
            del self.messages[chat_id]

    def add_message(
        self, chat_id: str, role: str, content: str, status: str = "completed"
    ) -> dict:
        with self.lock:
            if chat_id not in self.chats:
                raise ApiError(404, "CHAT_NOT_FOUND", "对话不存在")
            message = {
                "id": f"msg_{self.next_message_id}",
                "role": role,
                "content": content,
                "status": status,
                "created_time": self._time(),
            }
            self.next_message_id += 1
            self.messages[chat_id].append(message)
            if role == "user":
                self.chats[chat_id]["activity_time"] = self._time()
            return message.copy()

    def list_messages(
        self, chat_id: str, created_time_lt: str | None, page_size: int
    ) -> dict:
        with self.lock:
            if chat_id not in self.chats:
                raise ApiError(404, "CHAT_NOT_FOUND", "对话不存在")
            records = self.messages[chat_id]
            if created_time_lt:
                records = [
                    item for item in records if item["created_time"] < created_time_lt
                ]
            page = records[-page_size:]
            return {
                "items": [item.copy() for item in page],
                "has_more": len(records) > page_size,
            }

    def create_run(
        self, chat_id: str, content: str, client_message_id: str
    ) -> tuple[dict, bool]:
        with self.lock:
            if chat_id not in self.chats:
                raise ApiError(404, "CHAT_NOT_FOUND", "对话不存在")
            value = content.strip()
            if not value:
                raise ApiError(400, "INVALID_REQUEST", "消息内容不能为空")
            key = (chat_id, client_message_id)
            previous = self.idempotency.get(key)
            if previous:
                old_content, run_id, user_message = previous
                if old_content != value:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等键对应了不同消息")
                return {"run_id": run_id, "user_message": user_message.copy()}, False
            if chat_id in self.active_runs:
                raise ApiError(409, "CHAT_BUSY", "对话正在生成回复")
            user_message = self.add_message(chat_id, "user", value)
            assistant = self.add_message(chat_id, "assistant", "", "generating")
            run_id = f"run_{uuid4().hex}"
            self.runs[run_id] = {
                "id": run_id,
                "chat_id": chat_id,
                "assistant_message_id": assistant["id"],
                "prompt": value,
                "events": [],
                "status": "pending",
            }
            self.active_runs[chat_id] = run_id
            self.idempotency[key] = (value, run_id, user_message.copy())
            return {"run_id": run_id, "user_message": user_message}, True

    def append_event(self, run_id: str, event: str, data: dict) -> None:
        with self.lock:
            run = self.runs[run_id]
            run["events"].append({
                "id": str(len(run["events"]) + 1),
                "event": event,
                "data": data,
            })

    def run_snapshot(self, run_id: str, after_event_id: int) -> tuple[list[dict], str]:
        with self.lock:
            run = self.runs.get(run_id)
            if run is None:
                raise ApiError(404, "RUN_NOT_FOUND", "运行任务不存在")
            events = [
                event.copy() for event in run["events"]
                if int(event["id"]) > after_event_id
            ]
            return events, str(run["status"])

    def complete_run(self, run_id: str, final_content: str) -> dict:
        with self.lock:
            run = self.runs[run_id]
            chat_id = run["chat_id"]
            message_id = run["assistant_message_id"]
            message = next(
                item for item in self.messages[chat_id] if item["id"] == message_id
            )
            message["content"] = final_content
            message["status"] = "completed"
            run["status"] = "completed"
            self.chats[chat_id]["activity_time"] = self._time()
            self.active_runs.pop(chat_id, None)
            return message.copy()


async def generate_mock_reply(store: MockStore, run_id: str) -> None:
    with store.lock:
        run = store.runs[run_id]
        run["status"] = "running"
        message_id = run["assistant_message_id"]
        prompt = run["prompt"]
    store.append_event(
        run_id, "started",
        {"run_id": run_id, "assistant_message_id": message_id},
    )
    final_content = f"Mock 回复：{prompt}。"
    for chunk in split_stream_text(final_content):
        await asyncio.sleep(0.06)
        store.append_event(
            run_id, "delta",
            {"assistant_message_id": message_id, "delta": chunk},
        )
    final_message = store.complete_run(run_id, final_content)
    store.append_event(
        run_id, "completed",
        {"message": final_message, "finish_reason": "stop"},
    )


def split_stream_text(text: str, max_chunks: int = 80) -> list[str]:
    """Split mock output into small deterministic chunks for visible streaming."""
    if not text:
        return []
    chunk_size = max(2, math.ceil(len(text) / max_chunks))
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def format_sse(event: dict) -> str:
    data = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['event']}\ndata: {data}\n\n"


def create_app(*, seed: bool = True) -> FastAPI:
    app = FastAPI(title="Navi Mock Server", version="1.0")
    app.state.store = MockStore(seed=seed)
    app.state.tasks = set()

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, error: ApiError):
        return JSONResponse(
            status_code=error.status_code,
            content={
                "result": False,
                "data": None,
                "error": {"code": error.code, "message": error.message},
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _error: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "result": False,
                "data": None,
                "error": {"code": "INVALID_REQUEST", "message": "请求参数格式错误"},
            },
        )

    def validate_page_size(page_size: int) -> None:
        if not 1 <= page_size <= 100:
            raise ApiError(400, "INVALID_PAGE_SIZE", "page_size 必须在 1～100 之间")

    @app.get("/api/v1/chats")
    async def get_chats(activity_time_lt: str | None = None, page_size: int = 30):
        validate_page_size(page_size)
        return success(app.state.store.list_chats(activity_time_lt, page_size))

    @app.post("/api/v1/chats")
    async def create_chat(body: ChatCreate):
        return success(app.state.store.create_chat(body.name), 201)

    @app.patch("/api/v1/chats/{chat_id}")
    async def rename_chat(chat_id: str, body: ChatRename):
        return success(app.state.store.rename_chat(chat_id, body.name))

    @app.delete("/api/v1/chats/{chat_id}")
    async def delete_chat(chat_id: str):
        app.state.store.delete_chat(chat_id)
        return success({"id": chat_id})

    @app.get("/api/v1/chats/{chat_id}/messages")
    async def get_messages(
        chat_id: str, created_time_lt: str | None = None, page_size: int = 30
    ):
        validate_page_size(page_size)
        return success(
            app.state.store.list_messages(chat_id, created_time_lt, page_size)
        )

    @app.post("/api/v1/chats/{chat_id}/messages")
    async def send_message(chat_id: str, body: MessageCreate):
        data, created = app.state.store.create_run(
            chat_id, body.content, body.client_message_id
        )
        if created:
            task = asyncio.create_task(generate_mock_reply(app.state.store, data["run_id"]))
            app.state.tasks.add(task)
            task.add_done_callback(app.state.tasks.discard)
        return success(data, 202)

    @app.get("/api/v1/runs/{run_id}/events")
    async def run_events(
        run_id: str,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ):
        try:
            after_id = int(last_event_id or "0")
        except ValueError as error:
            raise ApiError(400, "INVALID_REQUEST", "Last-Event-ID 必须是整数") from error
        app.state.store.run_snapshot(run_id, after_id)

        async def event_stream():
            delivered = after_id
            heartbeat_ticks = 0
            while True:
                events, status = app.state.store.run_snapshot(run_id, delivered)
                for event in events:
                    delivered = int(event["id"])
                    yield format_sse(event)
                if status == "completed" and not events:
                    return
                await asyncio.sleep(0.05)
                heartbeat_ticks += 1
                if heartbeat_ticks >= 300:
                    heartbeat_ticks = 0
                    yield ": heartbeat\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},

        )

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporary in-memory Navi HTTP server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
