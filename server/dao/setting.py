"""model_setting 表的数据访问方法，只负责执行 SQL。"""

import sqlite3


SETTING_COLUMNS = """
setting_id, name, model_provider, model_name, api_key, base_url, active,
created_at, updated_at
"""

INSERT_SETTING_SQL = f"""
INSERT INTO model_setting ({SETTING_COLUMNS})
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_SETTING_SQL = f"""
SELECT {SETTING_COLUMNS}
FROM model_setting
WHERE setting_id = ?
"""

LIST_SETTINGS_SQL = """
SELECT setting_id, name, active
FROM model_setting
ORDER BY created_at DESC
"""

SELECT_ACTIVE_SETTING_SQL = f"""
SELECT {SETTING_COLUMNS}
FROM model_setting
WHERE active = 1
LIMIT 1
"""

UPDATE_SETTING_SQL = """
UPDATE model_setting
SET name = ?,
    model_provider = ?,
    model_name = ?,
    api_key = ?,
    base_url = ?,
    active = ?,
    updated_at = ?
WHERE setting_id = ?
"""

DEACTIVATE_SETTINGS_SQL = """
UPDATE model_setting
SET active = 0, updated_at = ?
WHERE active = 1 AND setting_id <> ?
"""

DELETE_SETTING_SQL = """
DELETE FROM model_setting
WHERE setting_id = ?
"""


def insert_setting(
    connection: sqlite3.Connection,
    *,
    setting_id: str,
    name: str,
    model_provider: str,
    model_name: str,
    api_key: str,
    base_url: str,
    active: bool,
    created_at: str,
    updated_at: str,
) -> None:
    """插入一条模型配置。"""
    connection.execute(
        INSERT_SETTING_SQL,
        (
            setting_id,
            name,
            model_provider,
            model_name,
            api_key,
            base_url,
            int(active),
            created_at,
            updated_at,
        ),
    )


def get_setting(
    connection: sqlite3.Connection,
    *,
    setting_id: str,
) -> dict | None:
    """按 ID 查询一条模型配置。"""
    row = connection.execute(SELECT_SETTING_SQL, (setting_id,)).fetchone()
    return dict(row) if row is not None else None


def get_settings(connection: sqlite3.Connection) -> list[dict]:
    """返回全部模型配置的 ID、名称和激活状态。"""
    rows = connection.execute(LIST_SETTINGS_SQL).fetchall()
    return [dict(row) for row in rows]


def get_active_setting(connection: sqlite3.Connection) -> dict | None:
    """查询当前唯一的激活配置。"""
    row = connection.execute(SELECT_ACTIVE_SETTING_SQL).fetchone()
    return dict(row) if row is not None else None


def deactivate_other_settings(
    connection: sqlite3.Connection,
    *,
    active_setting_id: str,
    updated_at: str,
) -> None:
    """取消目标配置以外的激活状态。"""
    connection.execute(
        DEACTIVATE_SETTINGS_SQL,
        (updated_at, active_setting_id),
    )


def update_setting(
    connection: sqlite3.Connection,
    *,
    setting_id: str,
    name: str,
    model_provider: str,
    model_name: str,
    api_key: str,
    base_url: str,
    active: bool,
    updated_at: str,
) -> dict | None:
    """覆盖一条模型配置的可修改字段并返回最新记录。"""
    cursor = connection.execute(
        UPDATE_SETTING_SQL,
        (
            name,
            model_provider,
            model_name,
            api_key,
            base_url,
            int(active),
            updated_at,
            setting_id,
        ),
    )
    if cursor.rowcount == 0:
        return None
    return get_setting(connection, setting_id=setting_id)


def delete_setting(
    connection: sqlite3.Connection,
    *,
    setting_id: str,
) -> bool:
    """删除指定配置并返回是否实际删除。"""
    cursor = connection.execute(DELETE_SETTING_SQL, (setting_id,))
    return cursor.rowcount > 0
