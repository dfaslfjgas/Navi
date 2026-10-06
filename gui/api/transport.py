"""GUI API 共用的 Qt HTTP 传输与响应解析。"""

import json
from collections.abc import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def response_data(payload) -> dict:
    """从统一成功响应中取出 data 对象。"""
    if not isinstance(payload, dict) or payload.get("result") is not True:
        raise ValueError("响应缺少成功标记")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("响应 data 必须是对象")
    return data


class ApiTransport(QObject):
    """统一发送普通 HTTP 请求，并把后端错误转换为 GUI 信号。"""

    request_failed = Signal(str, str)

    def __init__(self, base_url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.network = QNetworkAccessManager(self)

    def request(
        self,
        operation: str,
        method: str,
        path: str,
        payload: dict | None,
        on_success: Callable[[dict], None],
        *,
        timeout_ms: int = 5000,
    ) -> None:
        """发送 JSON 请求，并在 Qt 主线程中处理完成或失败结果。"""
        request = QNetworkRequest(QUrl(self.base_url + path))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/json",
        )
        request.setTransferTimeout(timeout_ms)
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else b""
        )
        if method == "GET":
            reply = self.network.get(request)
        elif method == "POST":
            reply = self.network.post(request, body)
        else:
            reply = self.network.sendCustomRequest(
                request,
                method.encode("ascii"),
                body,
            )

        def finished() -> None:
            raw = bytes(reply.readAll())
            try:
                response = json.loads(raw.decode("utf-8")) if raw.strip() else {}
                status = reply.attribute(
                    QNetworkRequest.Attribute.HttpStatusCodeAttribute
                )
                if reply.error() != QNetworkReply.NetworkError.NoError or (
                    status is not None and int(status) >= 400
                ):
                    self.request_failed.emit(
                        operation,
                        self.error_message(response, status, reply.errorString()),
                    )
                    return
                on_success(response)
            except (
                UnicodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
                KeyError,
            ) as error:
                self.request_failed.emit(
                    operation,
                    f"服务器响应格式错误：{error}",
                )
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    @staticmethod
    def error_message(payload, status, fallback: str) -> str:
        """优先读取后端统一错误结构，缺失时回退到 Qt 网络错误。"""
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                if code and message:
                    return f"{code}: {message}"
                if message:
                    return str(message)
        return fallback or f"HTTP {status}"
