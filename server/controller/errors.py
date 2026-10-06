"""Controller 共用的错误响应与原因日志。"""

import logging

from fastapi.responses import JSONResponse


LOGGER = logging.getLogger("navi.api.error")


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    operation: str,
) -> JSONResponse:
    """记录业务失败的明确原因并生成统一 JSON 错误响应。"""
    LOGGER.warning(
        "接口处理失败 operation=%s status=%s code=%s reason=%s",
        operation,
        status_code,
        code,
        message,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "result": False,
            "data": None,
            "error": {"code": code, "message": message},
        },
    )


def database_error(operation: str, message: str) -> JSONResponse:
    """在异常处理上下文中记录数据库堆栈并隐藏内部数据库细节。"""
    LOGGER.exception("数据库操作失败 operation=%s", operation)
    return JSONResponse(
        status_code=500,
        content={
            "result": False,
            "data": None,
            "error": {"code": "DATABASE_ERROR", "message": message},
        },
    )
