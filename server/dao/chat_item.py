"""chat_item 表的数据访问方法，只负责执行 SQL。"""

import sqlite3


INSERT_CHAT_ITEM_SQL = """
INSERT INTO chat_item (
    id,
    name,
    created_at,
    updated_at,
    activity_time
)
VALUES (?, ?, ?, ?, ?)
"""

RENAME_CHAT_ITEM_SQL = """
UPDATE chat_item
SET name = ?, updated_at = ?
WHERE id = ?
"""

SELECT_CHAT_ITEM_SQL = """
SELECT id, name, created_at, updated_at, activity_time
FROM chat_item
WHERE id = ?
"""

LIST_CHAT_ITEMS_SQL = """
SELECT id, name, created_at, updated_at, activity_time
FROM chat_item
ORDER BY activity_time DESC
LIMIT ?
"""

LIST_CHAT_ITEMS_BEFORE_SQL = """
SELECT id, name, created_at, updated_at, activity_time
FROM chat_item
WHERE activity_time < ?
ORDER BY activity_time DESC
LIMIT ?
"""

DELETE_CHAT_ITEM_SQL = """
DELETE FROM chat_item
WHERE id = ?
"""

def insert_chat_item(
    connection: sqlite3.Connection,
    *,
    chat_id: str,
    name: str,
    created_at: str,
    updated_at: str,
    activity_time: str,
) -> None:
    """向 chat_item 表插入一条对话记录。"""
    connection.execute(
        INSERT_CHAT_ITEM_SQL,
        (chat_id, name, created_at, updated_at, activity_time),
    )


def rename_chat_item(
    connection: sqlite3.Connection,
    *,
    chat_id: str,
    name: str,
    updated_at: str,
) -> dict[str, str] | None:
    """修改名称和更新时间；对话不存在时返回 None。"""
    cursor = connection.execute(
        RENAME_CHAT_ITEM_SQL,
        (name, updated_at, chat_id),
    )
    if cursor.rowcount == 0:
        return None

    row = connection.execute(SELECT_CHAT_ITEM_SQL, (chat_id,)).fetchone()
    return dict(row) if row is not None else None


def get_chat_items(
    connection: sqlite3.Connection,
    *,
    activity_time_lt: str | None,
    limit: int,
) -> list[dict[str, str]]:
    """按活动时间倒序查询一页对话记录。"""
    if activity_time_lt is None:
        rows = connection.execute(LIST_CHAT_ITEMS_SQL, (limit,)).fetchall()
    else:
        rows = connection.execute(
            LIST_CHAT_ITEMS_BEFORE_SQL,
            (activity_time_lt, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat_item(
    connection: sqlite3.Connection,
    *,
    chat_id: str,
) -> bool:
    """删除指定对话，并返回是否实际删除了一行。"""
    cursor = connection.execute(DELETE_CHAT_ITEM_SQL, (chat_id,))
    return cursor.rowcount > 0
