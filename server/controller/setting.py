"""模型设置 Controller：负责配置的创建、查询、修改和删除。"""

import sqlite3

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, model_validator

from server.controller.errors import api_error, database_error
from server.service.setting import (
    ModelTestError,
    create_setting as create_setting_service,
    delete_setting as delete_setting_service,
    get_setting as get_setting_service,
    get_settings as get_settings_service,
    test_setting as test_setting_service,
    update_setting as update_setting_service,
)


router = APIRouter(prefix="/setting", tags=["setting"])


class CreateSettingRequest(BaseModel):
    """新增模型配置时提交的完整数据。"""

    name: str = Field(min_length=1, max_length=100, description="配置名称")
    model_provider: str = Field(
        default="openai",
        min_length=1,
        max_length=64,
        description="LangChain 模型 Provider；OpenAI 兼容服务使用 openai",
    )
    model_name: str = Field(
        min_length=1,
        max_length=200,
        description="实际调用的模型名称",
    )
    api_key: str = Field(min_length=1, max_length=4096, description="API 密钥")
    base_url: str = Field(
        min_length=1,
        max_length=2048,
        description="模型服务基础地址",
    )
    active: bool = Field(description="是否立即激活该配置")


class UpdateSettingRequest(BaseModel):
    """修改模型配置时提交的数据；只需传入需要修改的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    model_provider: str | None = Field(default=None, min_length=1, max_length=64)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    active: bool | None = None

    @model_validator(mode="after")
    def require_changed_field(self):
        """拒绝完全为空的修改请求。"""
        if all(
            value is None
            for value in (
                self.name,
                self.model_provider,
                self.model_name,
                self.api_key,
                self.base_url,
                self.active,
            )
        ):
            raise ValueError("至少需要提供一个要修改的字段")
        return self


def _error_response(
    status_code: int,
    code: str,
    message: str,
    operation: str,
):
    """生成项目统一格式的错误响应。"""
    return api_error(
        status_code,
        code,
        message,
        operation=operation,
    )


def _database_error_response(operation: str):
    """记录数据库异常，并向 GUI 返回稳定且不泄露内部细节的错误。"""
    return database_error(
        operation,
        "模型配置读取或保存失败",
    )


@router.post(
    "/create_setting",
    status_code=status.HTTP_201_CREATED,
    summary="新增模型配置",
    description="新增一套模型调用配置；ID 由 Service 自动生成。",
)
def create_setting(body: CreateSettingRequest):
    """新增模型配置；active=true 时自动取消原激活配置。"""
    try:
        setting = create_setting_service(
            body.name,
            body.model_provider,
            body.model_name,
            body.api_key,
            body.base_url,
            body.active,
        )
    except ValueError as error:
        return _error_response(400, "INVALID_REQUEST", str(error), "新增模型配置")
    except sqlite3.Error:
        return _database_error_response("新增配置")
    return {"result": True, "data": setting, "error": None}


@router.delete(
    "/delete_setting/setting_id/{setting_id}",
    summary="删除模型配置",
    description="根据配置 ID 删除一套模型调用配置。",
)
def delete_setting(setting_id: str):
    """删除指定模型配置。"""
    try:
        deleted = delete_setting_service(setting_id)
    except ValueError as error:
        return _error_response(400, "INVALID_REQUEST", str(error), "删除模型配置")
    except LookupError as error:
        return _error_response(404, "SETTING_NOT_FOUND", str(error), "删除模型配置")
    except sqlite3.Error:
        return _database_error_response("删除配置")
    return {"result": True, "data": deleted, "error": None}


@router.get(
    "/get_setting",
    summary="获取全部模型配置",
    description="只返回配置 ID、名称和激活状态，并保持按创建时间排列。",
)
def get_setting():
    """获取配置摘要，不返回模型名称、密钥和地址等详情。"""
    try:
        items = get_settings_service()
    except sqlite3.Error:
        return _database_error_response("获取配置")
    return {
        "result": True,
        "data": items,
        "error": None,
    }


@router.get(
    "/get_setting/setting_id/{setting_id}",
    summary="获取模型配置详情",
    description="根据配置 ID 返回该配置的全部信息。",
)
def get_setting_detail(setting_id: str):
    """获取一条模型配置的完整信息，包括明文 API Key。"""
    try:
        setting = get_setting_service(setting_id)
    except ValueError as error:
        return _error_response(400, "INVALID_REQUEST", str(error), "获取模型配置详情")
    except LookupError as error:
        return _error_response(404, "SETTING_NOT_FOUND", str(error), "获取模型配置详情")
    except sqlite3.Error:
        return _database_error_response("获取配置详情")
    return {"result": True, "data": setting, "error": None}


@router.post(
    "/test_setting",
    summary="测试当前模型配置",
    description="使用当前激活配置发起一次最小模型调用，验证模型、密钥和地址。",
)
async def test_setting():
    """测试服务启动时加载且随激活选择实时更新的模型配置。"""
    try:
        result = await test_setting_service()
    except ValueError as error:
        return _error_response(400, "INVALID_REQUEST", str(error), "测试激活模型配置")
    except LookupError as error:
        return _error_response(404, "SETTING_NOT_FOUND", str(error), "测试激活模型配置")
    except ModelTestError as error:
        return _error_response(
            502,
            "MODEL_CONNECTION_FAILED",
            str(error),
            "测试激活模型配置",
        )
    except sqlite3.Error:
        return _database_error_response("测试配置")
    return {"result": True, "data": result, "error": None}


@router.patch(
    "/update_setting/setting_id/{setting_id}",
    summary="修改模型配置",
    description="根据配置 ID 修改请求体中提供的字段。",
)
def update_setting(setting_id: str, body: UpdateSettingRequest):
    """部分修改模型配置；active=true 时自动切换激活配置。"""
    try:
        setting = update_setting_service(
            setting_id,
            name=body.name,
            model_provider=body.model_provider,
            model_name=body.model_name,
            api_key=body.api_key,
            base_url=body.base_url,
            active=body.active,
        )
    except ValueError as error:
        return _error_response(400, "INVALID_REQUEST", str(error), "修改模型配置")
    except LookupError as error:
        return _error_response(404, "SETTING_NOT_FOUND", str(error), "修改模型配置")
    except sqlite3.Error:
        return _database_error_response("修改配置")
    return {"result": True, "data": setting, "error": None}
