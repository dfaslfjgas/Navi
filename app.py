"""Navi launcher: run FastAPI as a child process owned by the Qt process."""

from pathlib import Path
import subprocess
import sys

from gui.main import main as gui_main


PROJECT_ROOT = Path(__file__).resolve().parent


def start_server() -> subprocess.Popen:
    """使用与 Qt 相同的 Python 环境启动本地 FastAPI 子进程。"""
    return subprocess.Popen(
        [sys.executable, "-m", "server.main"],
        cwd=PROJECT_ROOT,
    )


def stop_server(process: subprocess.Popen, timeout: float = 5.0) -> None:
    """终止并回收 FastAPI，确保 Qt 退出后不会残留服务进程。"""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    """先启动 FastAPI，再运行 Qt；无论 Qt 如何结束都清理子进程。"""
    server_process = start_server()
    try:
        return gui_main()
    finally:
        stop_server(server_process)


if __name__ == "__main__":
    raise SystemExit(main())
