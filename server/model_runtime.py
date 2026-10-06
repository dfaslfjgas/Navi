"""进程内当前模型配置，供 Agent 和配置测试共用。"""

from threading import RLock


ACTIVE_MODEL_SETTING: dict | None = None
_LOCK = RLock()


def set_active_model_setting(setting: dict | None) -> None:
    """保存当前激活配置的副本；取消激活时明确设置为 None。"""
    global ACTIVE_MODEL_SETTING
    with _LOCK:
        ACTIVE_MODEL_SETTING = dict(setting) if setting is not None else None


def get_active_model_setting() -> dict | None:
    """返回当前激活配置的副本。"""
    with _LOCK:
        return (
            dict(ACTIVE_MODEL_SETTING)
            if ACTIVE_MODEL_SETTING is not None
            else None
        )
