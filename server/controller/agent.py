"""Agent Controller：负责提交用户消息以及通过 SSE 推送 Agent 回复。"""

from fastapi import APIRouter, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


router = APIRouter(tags=["agent"])


class SendMessageRequest(BaseModel):
    """GUI 提交给 Agent 的消息。"""

    content: str = Field(description="用户输入的消息内容")
    client_message_id: str = Field(
        description="GUI 生成的唯一 ID，用于防止重试产生重复消息"
    )


@router.post(
    "/chats/{chat_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    summary="发送消息给 Agent",
    description="保存用户消息、创建 Agent 运行任务，并返回用于连接 SSE 的 run_id。",
)
async def send_message(chat_id: str, body: SendMessageRequest):
    """接受一条用户消息并启动对应的 Agent 回复任务。"""
    pass


@router.get(
    "/runs/{run_id}/events",
    response_class=StreamingResponse,
    summary="接收 Agent 流式回复",
    description="使用 SSE 持续推送 started、delta、completed 或 error 事件。",
)
async def stream_agent_events(
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """推送 Agent 运行事件，并支持通过 Last-Event-ID 从断点继续。"""
    pass
