"""大模型配置业务逻辑。"""

import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
from uuid import uuid4

from server.dao.setting import (
    deactivate_other_settings,
    delete_setting as delete_setting_dao,
    get_active_setting as get_active_setting_dao,
    get_setting as get_setting_dao,
    get_settings as get_settings_dao,
    insert_setting,
    update_setting as update_setting_dao,
)
from server.database import connect_database
from server.model_runtime import get_active_model_setting, set_active_model_setting


MODEL_TEST_PROMPT = "这是一次连接测试，请只回复 OK。"
MODEL_TEST_TIMEOUT_SECONDS = 20
MODEL_PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SUPPORTED_MODEL_PROVIDERS = {
    "anthropic",
    "google_genai",
    "openai",
}


class ModelTestError(RuntimeError):
    """模型配置可以读取，但初始化或调用测试失败。"""


def _init_chat_model(**kwargs):
    """延迟导入 LangChain，避免数据库接口依赖模型包的导入时机。"""
    from langchain.chat_models import init_chat_model

    return init_chat_model(**kwargs)


def utc_now() -> str:
    """生成 UTC RFC 3339 微秒时间。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _required_text(value: str, label: str, maximum: int) -> str:
    """去除首尾空格并校验必填文本。"""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}不能为空")
    if len(normalized) > maximum:
        raise ValueError(f"{label}不能超过 {maximum} 个字符")
    return normalized


def _normalize_base_url(value: str) -> str:
    """校验模型地址，并移除末尾斜杠以便后续拼接路径。"""
    normalized = _required_text(value, "模型地址", 2048).rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("模型地址必须是有效的 http 或 https URL")
    return normalized


def _normalize_model_provider(value: str) -> str:
    """规范 LangChain Provider 名称，具体选项后续由 GUI 下拉框提供。"""
    normalized = _required_text(value, "Model Provider", 64).lower()
    if not MODEL_PROVIDER_PATTERN.fullmatch(normalized):
        raise ValueError("Model Provider 格式无效")
    if normalized not in SUPPORTED_MODEL_PROVIDERS:
        raise ValueError(f"不支持的 Model Provider：{normalized}")
    return normalized


def _serialize(record: dict) -> dict:
    """把 SQLite 整数布尔值转换成接口使用的 bool。"""
    result = dict(record)
    result["active"] = bool(result["active"])
    return result


def create_setting(
    name: str,
    model_provider: str,
    model_name: str,
    api_key: str,
    base_url: str,
    active: bool,
    *,
    database_path: Path | None = None,
) -> dict:
    """校验并创建模型配置；激活时自动取消原激活配置。"""
    normalized_name = _required_text(name, "配置名称", 100)
    normalized_provider = _normalize_model_provider(model_provider)
    normalized_model = _required_text(model_name, "模型名称", 200)
    normalized_key = _required_text(api_key, "API Key", 4096)
    normalized_url = _normalize_base_url(base_url)
    setting_id = f"setting_{uuid4().hex}"
    now = utc_now()

    try:
        with closing(connect_database(database_path)) as connection:
            with connection:
                if active:
                    deactivate_other_settings(
                        connection,
                        active_setting_id=setting_id,
                        updated_at=now,
                    )
                insert_setting(
                    connection,
                    setting_id=setting_id,
                    name=normalized_name,
                    model_provider=normalized_provider,
                    model_name=normalized_model,
                    api_key=normalized_key,
                    base_url=normalized_url,
                    active=active,
                    created_at=now,
                    updated_at=now,
                )
    except sqlite3.IntegrityError as error:
        if "model_setting.name" in str(error):
            raise ValueError("配置名称已存在") from error
        raise

    load_active_setting(database_path=database_path)
    return {
        "setting_id": setting_id,
        "name": normalized_name,
        "model_provider": normalized_provider,
        "model_name": normalized_model,
        "api_key": normalized_key,
        "base_url": normalized_url,
        "active": active,
        "created_at": now,
        "updated_at": now,
    }


def get_settings(*, database_path: Path | None = None) -> list[dict]:
    """返回全部模型配置的 ID、名称和激活状态。"""
    with closing(connect_database(database_path)) as connection:
        return [
            {**item, "active": bool(item["active"])}
            for item in get_settings_dao(connection)
        ]


def load_active_setting(*, database_path: Path | None = None) -> dict | None:
    """从 SQLite 加载激活配置并更新进程内运行时状态。"""
    with closing(connect_database(database_path)) as connection:
        setting = get_active_setting_dao(connection)
    serialized = _serialize(setting) if setting is not None else None
    set_active_model_setting(serialized)
    return serialized


def get_setting(
    setting_id: str,
    *,
    database_path: Path | None = None,
) -> dict:
    """根据 ID 返回一条模型配置的完整信息。"""
    normalized_id = setting_id.strip()
    if not normalized_id:
        raise ValueError("配置 ID 不能为空")
    with closing(connect_database(database_path)) as connection:
        setting = get_setting_dao(
            connection,
            setting_id=normalized_id,
        )
    if setting is None:
        raise LookupError("模型配置不存在")
    return _serialize(setting)


async def test_setting() -> dict:
    """使用进程内当前激活配置发起一次最小模型调用。"""
    setting = get_active_model_setting()
    if setting is None:
        raise LookupError("当前没有激活的模型配置")

    required_fields = {
        "setting_id": "配置 ID",
        "model_provider": "Model Provider",
        "model_name": "模型名称",
        "api_key": "API Key",
        "base_url": "模型地址",
    }
    missing_fields = [
        label
        for field, label in required_fields.items()
        if not str(setting.get(field) or "").strip()
    ]
    if missing_fields:
        raise ValueError(
            "当前激活模型配置缺少必要参数：" + "、".join(missing_fields)
        )

    try:
        model = _init_chat_model(
            model=setting["model_name"],
            model_provider=setting["model_provider"],
            api_key=setting["api_key"],
            base_url=setting["base_url"],
            temperature=0,
            timeout=15,
            max_retries=0,
        )
        message = await asyncio.wait_for(
            model.ainvoke(MODEL_TEST_PROMPT),
            timeout=MODEL_TEST_TIMEOUT_SECONDS,
        )
    except Exception as error:
        raise ModelTestError(f"模型配置测试失败：{error}") from error

    content = getattr(message, "content", message)
    if isinstance(content, list):
        reply = "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part)
            for part in content
        )
    else:
        reply = str(content)
    return {
        "setting_id": setting["setting_id"],
        "success": True,
        "reply": reply,
    }


def update_setting(
    setting_id: str,
    *,
    name: str | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    active: bool | None = None,
    database_path: Path | None = None,
) -> dict:
    """只修改请求中提供的字段；激活时取消其他配置。"""
    normalized_id = setting_id.strip()
    if not normalized_id:
        raise ValueError("配置 ID 不能为空")

    try:
        with closing(connect_database(database_path)) as connection:
            with connection:
                existing = get_setting_dao(
                    connection,
                    setting_id=normalized_id,
                )
                if existing is None:
                    raise LookupError("模型配置不存在")

                next_name = (
                    _required_text(name, "配置名称", 100)
                    if name is not None
                    else existing["name"]
                )
                next_provider = (
                    _normalize_model_provider(model_provider)
                    if model_provider is not None
                    else existing["model_provider"]
                )
                next_model = (
                    _required_text(model_name, "模型名称", 200)
                    if model_name is not None
                    else existing["model_name"]
                )
                next_key = (
                    _required_text(api_key, "API Key", 4096)
                    if api_key is not None
                    else existing["api_key"]
                )
                next_url = (
                    _normalize_base_url(base_url)
                    if base_url is not None
                    else existing["base_url"]
                )
                next_active = (
                    active if active is not None else bool(existing["active"])
                )
                now = utc_now()
                if next_active:
                    deactivate_other_settings(
                        connection,
                        active_setting_id=normalized_id,
                        updated_at=now,
                    )
                updated = update_setting_dao(
                    connection,
                    setting_id=normalized_id,
                    name=next_name,
                    model_provider=next_provider,
                    model_name=next_model,
                    api_key=next_key,
                    base_url=next_url,
                    active=next_active,
                    updated_at=now,
                )
    except sqlite3.IntegrityError as error:
        if "model_setting.name" in str(error):
            raise ValueError("配置名称已存在") from error
        raise

    if updated is None:
        raise LookupError("模型配置不存在")
    load_active_setting(database_path=database_path)
    return _serialize(updated)


def delete_setting(
    setting_id: str,
    *,
    database_path: Path | None = None,
) -> dict[str, str]:
    """删除指定模型配置。"""
    normalized_id = setting_id.strip()
    if not normalized_id:
        raise ValueError("配置 ID 不能为空")
    with closing(connect_database(database_path)) as connection:
        with connection:
            deleted = delete_setting_dao(
                connection,
                setting_id=normalized_id,
            )
    if not deleted:
        raise LookupError("模型配置不存在")
    load_active_setting(database_path=database_path)
    return {"setting_id": normalized_id}
