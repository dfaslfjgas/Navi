"""聊天内容业务逻辑。"""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from server.dao.chat_content import (
    chat_item_exists,
    get_chat_content as get_chat_content_dao,
    insert_chat_content,
    update_chat_activity,
)
from server.database import connect_database


MESSAGE_ROLES = {"user", "assistant", "system"}
MESSAGE_STATUSES = {"generating", "completed", "failed"}
MESSAGE_PAGE_SIZE = 30


def utc_now() -> str:
    """生成 UTC RFC 3339 微秒时间。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def add_chat_content(
    chat_id: str,
    role: str,
    content: str,
    *,
    status: str = "completed",
    database_path: Path | None = None,
) -> dict[str, str]:
    """校验并保存一条消息，同时更新所属对话的活动时间。"""
    if not chat_id:
        raise ValueError("对话 ID 不能为空")
    if role not in MESSAGE_ROLES:
        raise ValueError("消息角色必须是 user、assistant 或 system")
    if status not in MESSAGE_STATUSES:
        raise ValueError("消息状态无效")
    if status != "generating" and not content.strip():
        raise ValueError("消息内容不能为空")

    content_id = f"msg_{uuid4().hex}"
    created_time = utc_now()

    with closing(connect_database(database_path)) as connection:
        with connection:
            if not update_chat_activity(
                connection,
                chat_id=chat_id,
                activity_time=created_time,
            ):
                raise LookupError("对话不存在")
            insert_chat_content(
                connection,
                content_id=content_id,
                chat_id=chat_id,
                role=role,
                content=content,
                status=status,
                created_time=created_time,
            )

    return {
        "id": content_id,
        "role": role,
        "content": content,
        "status": status,
        "created_time": created_time,
    }


def get_chat_content(
    chat_id: str,
    created_time_lt: str | None = None,
    page_size: int = MESSAGE_PAGE_SIZE,
    *,
    database_path: Path | None = None,
) -> dict[str, object]:
    """获取最新消息或指定时间之前的消息，每页最多 30 条。"""
    if not chat_id:
        raise ValueError("对话 ID 不能为空")
    if not 1 <= page_size <= MESSAGE_PAGE_SIZE:
        raise ValueError("page_size 必须在 1～30 之间")
    if created_time_lt is not None and not created_time_lt.strip():
        raise ValueError("created_time_lt 不能为空")

    with closing(connect_database(database_path)) as connection:
        if not chat_item_exists(connection, chat_id):
            raise LookupError("对话不存在")
        records = get_chat_content_dao(
            connection,
            chat_id=chat_id,
            created_time_lt=created_time_lt,
            limit=page_size + 1,
        )

    has_more = len(records) > page_size
    items = records[:page_size]
    items.reverse()
    return {
        "items": items,
        "has_more": has_more,
    }
