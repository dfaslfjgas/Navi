"""对话列表 Controller：负责对话项的查询、创建、重命名和删除。"""

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from server.controller.errors import api_error
from server.service.chat_item import (
    create_chat_item as create_chat_item_service,
    delete_chat_item as delete_chat_item_service,
    get_chat_items as get_chat_items_service,
    rename_chat_item as rename_chat_item_service,
)


router = APIRouter(prefix="/chats", tags=["chat-item"])


class CreateChatRequest(BaseModel):
    """创建对话时提交的数据。"""

    name: str | None = Field(
        default=None,
        max_length=100,
        description="对话名称；不传时由 Service 使用默认名称“新对话”",
    )


class RenameChatRequest(BaseModel):
    """重命名对话时提交的数据。"""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="新的对话名称",
    )


@router.get(
    "",
    summary="获取对话列表",
    description="按 activity_time 从新到旧分页返回对话列表。",
)
def get_chat_items(
    activity_time_lt: str | None = Query(
        default=None,
        description="只查询活动时间早于该时间的对话；首次加载时不传",
    ),
    page_size: int = Query(
        default=30,
        ge=1,
        le=100,
        description="本次最多返回的对话数量",
    ),
):
    """获取最新一页对话，或继续加载指定时间之前的对话。"""
    try:
        data = get_chat_items_service(activity_time_lt, page_size)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="获取对话列表",
        )

    return {
        "result": True,
        "data": data,
        "error": None,
    }


@router.post("",
             status_code=status.HTTP_201_CREATED,
             summary="新建对话",
             description="创建一个空对话，并返回新建的对话列表项。",)
def create_chat_item(body: CreateChatRequest):
    """创建对话；名称为空时由 Service 设置默认名称。"""
    try:
        chat_item = create_chat_item_service(body.name)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="创建对话",
        )

    return {
        "result": True,
        "data": chat_item,
        "error": None,
    }


@router.patch(
    "/{chat_id}",
    summary="重命名对话",
    description="修改指定对话的名称，但不改变对话的活动时间和排序。",
)
def rename_chat_item(chat_id: str, body: RenameChatRequest):
    """修改指定对话的显示名称。"""
    try:
        chat_item = rename_chat_item_service(chat_id, body.name)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="重命名对话",
        )
    except LookupError as error:
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            str(error),
            operation="重命名对话",
        )

    return {
        "result": True,
        "data": chat_item,
        "error": None,
    }


@router.delete(
    "/{chat_id}",
    summary="删除对话",
    description="删除指定对话；对应的全部聊天内容由 Service/DAO 一并删除。",
)
def delete_chat_item(chat_id: str):
    """删除一个对话及其关联内容。"""
    try:
        deleted = delete_chat_item_service(chat_id)
    except ValueError as error:
        return api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_REQUEST",
            str(error),
            operation="删除对话",
        )
    except LookupError as error:
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            str(error),
            operation="删除对话",
        )

    return {
        "result": True,
        "data": deleted,
        "error": None,
    }
