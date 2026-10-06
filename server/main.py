"""Navi FastAPI 子进程入口。"""

from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError

from common.config import AppConfig
from server.controller import api_router
from server.database import initialize_database
from server.logging_config import configure_server_logging, shutdown_server_logging
from server.service.setting import load_active_setting


LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_application: FastAPI):
    """初始化 SQLite，并在接收请求前加载当前激活模型配置。"""
    log_path = configure_server_logging()
    database_path = initialize_database()
    active_setting = load_active_setting()
    LOGGER.info("SQLite 初始化完成：%s", database_path)
    if active_setting is None:
        LOGGER.warning("启动时没有找到 active=true 的模型配置")
    else:
        LOGGER.info(
            "已加载激活模型配置：setting_id=%s name=%s provider=%s model=%s",
            active_setting["setting_id"],
            active_setting["name"],
            active_setting["model_provider"],
            active_setting["model_name"],
        )
    LOGGER.info("服务端日志文件：%s", log_path)
    try:
        yield
    finally:
        LOGGER.info("Navi Server 正在停止")
        shutdown_server_logging()


def create_app() -> FastAPI:
    """创建 FastAPI 应用并挂载所有版本化业务路由。"""
    application = FastAPI(
        title="Navi Server",
        version="1.0.0",
        description="Navi GUI 使用的本地 HTTP 与 SSE 服务。",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def log_http_request(request: Request, call_next):
        """记录请求结果和耗时，不记录可能包含 API Key 的请求体。"""
        request_id = uuid4().hex[:12]
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (perf_counter() - started) * 1000
            LOGGER.exception(
                "HTTP 请求未处理异常 request_id=%s method=%s path=%s elapsed_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (perf_counter() - started) * 1000
        log = LOGGER.warning if response.status_code >= 400 else LOGGER.info
        log(
            "HTTP request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def log_request_validation_error(
        request: Request,
        error: RequestValidationError,
    ):
        """记录 422 的字段位置和原因，但不记录字段值。"""
        safe_errors = [
            {
                "field": ".".join(str(part) for part in item.get("loc", ())),
                "reason": item.get("msg", "参数无效"),
                "type": item.get("type", "validation_error"),
            }
            for item in error.errors()
        ]
        LOGGER.warning(
            "请求参数校验失败 method=%s path=%s errors=%s",
            request.method,
            request.url.path,
            safe_errors,
        )
        return await request_validation_exception_handler(request, error)

    application.include_router(api_router)
    return application


app = create_app()


def main() -> None:
    """仅监听本机地址，由根目录 app.py 作为子进程启动。"""
    config = AppConfig()
    configure_server_logging()
    uvicorn.run(
        app,
        host=config.agent_host,
        port=config.agent_port,
        log_level="info",
        log_config=None,
    )


if __name__ == "__main__":
    main()
