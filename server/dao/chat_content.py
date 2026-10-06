"""chat_content 表的数据访问方法，只负责执行 SQL。"""

import sqlite3


CHAT_ITEM_EXISTS_SQL = """
SELECT 1
FROM chat_item
WHERE id = ?
"""

INSERT_CHAT_CONTENT_SQL = """
INSERT INTO chat_content (
    content_id,
    chat_id,
    role,
    content,
    status,
    created_time
)
VALUES (?, ?, ?, ?, ?, ?)
"""

LIST_CHAT_CONTENT_SQL = """
SELECT content_id AS id, role, content, status, created_time
FROM chat_content
WHERE chat_id = ?
ORDER BY created_time DESC
LIMIT ?
"""

LIST_CHAT_CONTENT_BEFORE_SQL = """
SELECT content_id AS id, role, content, status, created_time
FROM chat_content
WHERE chat_id = ? AND created_time < ?
ORDER BY created_time DESC
LIMIT ?
"""

UPDATE_CHAT_ACTIVITY_SQL = """
UPDATE chat_item
SET activity_time = ?
WHERE id = ?
"""


def chat_item_exists(connection: sqlite3.Connection, chat_id: str) -> bool:
    """判断指定对话是否存在。"""
    return connection.execute(CHAT_ITEM_EXISTS_SQL, (chat_id,)).fetchone() is not None


def insert_chat_content(
    connection: sqlite3.Connection,
    *,
    content_id: str,
    chat_id: str,
    role: str,
    content: str,
    status: str,
    created_time: str,
) -> None:
    """插入一条消息。"""
    connection.execute(
        INSERT_CHAT_CONTENT_SQL,
        (content_id, chat_id, role, content, status, created_time),
    )


def update_chat_activity(
    connection: sqlite3.Connection,
    *,
    chat_id: str,
    activity_time: str,
) -> bool:
    """更新对话活动时间，并返回对话是否存在。"""
    cursor = connection.execute(
        UPDATE_CHAT_ACTIVITY_SQL,
        (activity_time, chat_id),
    )
    return cursor.rowcount > 0


def get_chat_content(
    connection: sqlite3.Connection,
    *,
    chat_id: str,
    created_time_lt: str | None,
    limit: int,
) -> list[dict[str, str]]:
    """按创建时间倒序查询指定对话的消息。"""
    if created_time_lt is None:
        rows = connection.execute(
            LIST_CHAT_CONTENT_SQL,
            (chat_id, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            LIST_CHAT_CONTENT_BEFORE_SQL,
            (chat_id, created_time_lt, limit),
        ).fetchall()
    return [dict(row) for row in rows]
