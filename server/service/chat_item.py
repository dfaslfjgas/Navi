"""对话列表业务逻辑。"""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from server.dao.chat_item import (
    delete_chat_item as delete_chat_item_dao,
    get_chat_items as get_chat_items_dao,
    insert_chat_item,
    rename_chat_item as rename_chat_item_dao,
)
from server.database import connect_database


DEFAULT_CHAT_NAME = "新对话"
MAX_CHAT_NAME_LENGTH = 100


def utc_now() -> str:
    """生成与 HTTP 接口约定一致的 UTC RFC 3339 微秒时间。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def normalize_chat_name(name: str | None) -> str:
    """处理默认名称，并拒绝纯空白或过长的对话名称。"""
    if name is None:
        return DEFAULT_CHAT_NAME

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("对话名称不能为空")
    if len(normalized_name) > MAX_CHAT_NAME_LENGTH:
        raise ValueError("对话名称不能超过 100 个字符")
    return normalized_name


def normalize_required_chat_name(name: str) -> str:
    """校验必须提供的对话名称，用于重命名等操作。"""
    if name is None:
        raise ValueError("对话名称不能为空")

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("对话名称不能为空")
    if len(normalized_name) > MAX_CHAT_NAME_LENGTH:
        raise ValueError("对话名称不能超过 100 个字符")
    return normalized_name


def create_chat_item(
    name: str | None,
    *,
    database_path: Path | None = None,
) -> dict[str, str]:
    """校验名称，在一个事务中创建对话，并返回新记录。"""
    normalized_name = normalize_chat_name(name)
    chat_id = f"chat_{uuid4().hex}"
    now = utc_now()

    with closing(connect_database(database_path)) as connection:
        with connection:
            insert_chat_item(
                connection,
                chat_id=chat_id,
                name=normalized_name,
                created_at=now,
                updated_at=now,
                activity_time=now,
            )

    return {
        "id": chat_id,
        "name": normalized_name,
        "created_at": now,
        "updated_at": now,
        "activity_time": now,
    }


def rename_chat_item(
    chat_id: str,
    name: str,
    *,
    database_path: Path | None = None,
) -> dict[str, str]:
    """校验重命名参数，只修改名称和更新时间。"""
    normalized_chat_id = chat_id.strip()
    if not normalized_chat_id:
        raise ValueError("对话 ID 不能为空")
    normalized_name = normalize_required_chat_name(name)
    updated_at = utc_now()

    with closing(connect_database(database_path)) as connection:
        with connection:
            updated = rename_chat_item_dao(
                connection,
                chat_id=normalized_chat_id,
                name=normalized_name,
                updated_at=updated_at,
            )

    if updated is None:
        raise LookupError("对话不存在")
    return updated


def get_chat_items(
    activity_time_lt: str | None = None,
    page_size: int = 30,
    *,
    database_path: Path | None = None,
) -> dict[str, list[dict[str, str]] | bool]:
    """按活动时间倒序获取对话，并计算是否还有下一页。"""
    if not 1 <= page_size <= 100:
        raise ValueError("page_size 必须在 1～100 之间")
    if activity_time_lt is not None and not activity_time_lt.strip():
        raise ValueError("activity_time_lt 不能为空")

    with closing(connect_database(database_path)) as connection:
        records = get_chat_items_dao(
            connection,
            activity_time_lt=activity_time_lt,
            limit=page_size + 1,
        )

    has_more = len(records) > page_size
    return {
        "items": records[:page_size],
        "has_more": has_more,
    }


def delete_chat_item(
    chat_id: str,
    *,
    database_path: Path | None = None,
) -> dict[str, str]:
    """删除指定对话；对话不存在时抛出 LookupError。"""
    if not chat_id:
        raise ValueError("对话 ID 不能为空")

    with closing(connect_database(database_path)) as connection:
        with connection:
            deleted = delete_chat_item_dao(connection, chat_id=chat_id)

    if not deleted:
        raise LookupError("对话不存在")
    return {"id": chat_id}
