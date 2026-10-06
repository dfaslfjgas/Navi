"""Navi Server 日志配置：控制台输出、文件轮换和标准日志接管。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from server.database import get_database_path


LOG_FILE_NAME = "navi-server.log"
LOG_ROTATION_SIZE = "10 MB"
LOG_RETENTION = "14 days"
_configured_path: Path | None = None


class _InterceptHandler(logging.Handler):
    """把 logging/uvicorn/FastAPI 日志转交给 Loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        from loguru import logger

        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def get_log_path() -> Path:
    """日志与 SQLite 数据放在同一个 Navi 应用数据目录下。"""
    return get_database_path().parent / "logs" / LOG_FILE_NAME


def _configure_standard_fallback(log_path: Path) -> None:
    """Loguru 尚未安装时保持应用可启动，并提供基础大小轮换。"""
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[console, file_handler],
        force=True,
    )
    logging.getLogger(__name__).warning(
        "未安装 Loguru，当前使用标准日志轮换；请安装 requirements.txt 中的依赖"
    )


def configure_server_logging() -> Path:
    """配置服务端日志；重复调用同一路径时不会重复添加处理器。"""
    global _configured_path
    log_path = get_log_path()
    if _configured_path == log_path:
        return log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from loguru import logger
    except ImportError:
        _configure_standard_fallback(log_path)
    else:
        logger.remove()
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
        )
        logger.add(
            sys.stderr,
            level="INFO",
            format=log_format,
            colorize=True,
            backtrace=False,
            diagnose=False,
        )
        logger.add(
            log_path,
            level="INFO",
            format=log_format,
            colorize=False,
            rotation=LOG_ROTATION_SIZE,
            retention=LOG_RETENTION,
            compression="zip",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
        )
        logging.basicConfig(
            handlers=[_InterceptHandler()],
            level=logging.INFO,
            force=True,
        )
        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
            target = logging.getLogger(logger_name)
            target.handlers = [_InterceptHandler()]
            target.propagate = False
    _configured_path = log_path
    logging.getLogger(__name__).info("日志系统已初始化：%s", log_path)
    return log_path


def shutdown_server_logging() -> None:
    """刷新并关闭日志处理器，避免 Windows 持续占用轮换日志文件。"""
    global _configured_path

    try:
        from loguru import logger
    except ImportError:
        pass
    else:
        # remove() 会等待文件 sink 写完并关闭对应文件句柄。
        logger.remove()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        try:
            handler.flush()
            handler.close()
        finally:
            root_logger.removeHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        target = logging.getLogger(logger_name)
        for handler in target.handlers[:]:
            try:
                handler.flush()
                handler.close()
            finally:
                target.removeHandler(handler)

    _configured_path = None
