"""聊天内容 Controller：负责新增消息和分页读取历史消息。"""

from typing import Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from server.controller.errors import api_error
from server.service.chat_content import (
    add_chat_content as add_chat_content_service,
    get_chat_content as get_chat_content_service,
)


router = APIRouter(prefix="/chat_content", tags=["chat-content"])


class AddChatContentRequest(BaseModel):
    """新增一条聊天消息时提交的数据。"""

    role: Literal["user", "assistant", "system"] = Field(
        description="消息发送方"
    )
    content: str = Field(description="消息正文")


@router.get(
    "/{chat_id}/messages",
    summary="获取聊天内容",
    description="读取指定对话的最新消息，或继续加载某个时间之前的历史消息。",
)
def get_chat_content(
    chat_id: str,
    created_time_lt: str | None = Query(
        default=None,
        description="只查询创建时间早于该时间的消息；首次加载时不传",
    ),
    page_size: int = Query(
        default=30,
        ge=1,
        le=30,
        description="本次返回的消息数量，最多 30 条",
    ),
):
    """按时间分页获取消息，返回给 GUI 后按从旧到新的顺序展示。"""
    try:
        data = get_chat_content_service(chat_id, created_time_lt, page_size)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="获取聊天内容",
        )
    except LookupError as error:
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            str(error),
            operation="获取聊天内容",
        )

    return {
        "result": True,
        "data": data,
        "error": None,
    }


@router.post(
    "/{chat_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="增加聊天消息",
    description="向指定对话增加一条消息，并更新对话活动时间。",
)
def add_chat_content(chat_id: str, body: AddChatContentRequest):
    """增加一条用户、助手或系统消息。"""
    try:
        message = add_chat_content_service(chat_id, body.role, body.content)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="增加聊天消息",
        )
    except LookupError as error:
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            str(error),
            operation="增加聊天消息",
        )

    return {
        "result": True,
        "data": message,
        "error": None,
    }
