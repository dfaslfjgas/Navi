"""Manual Qt-to-FastAPI round trip check against a running mock server."""

import json
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QTimer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gui.api import NaviApi


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/api/v1"
    app = QCoreApplication([])
    api = NaviApi(base_url, app)
    result = {"events": [], "delta": ""}
    failed = {"value": False}

    def finish_failure(operation: str, detail: str) -> None:
        failed["value"] = True
        result["error"] = {"operation": operation, "detail": detail}
        app.quit()

    def chats_loaded(items: list, _has_more: bool, _is_more: bool) -> None:
        if not items:
            finish_failure("chats", "mock server returned no chats")
            return
        result["chat_id"] = items[0]["id"]
        api.agent.send_message(items[0]["id"], "Qt SSE 联调")

    def accepted(_chat_id: str, run_id: str, _message: dict) -> None:
        result["run_id"] = run_id
        result["events"].append("accepted")

    def started(_run_id: str, _message_id: str) -> None:
        result["events"].append("started")

    def delta(_run_id: str, _message_id: str, text: str) -> None:
        result["events"].append("delta")
        result["delta"] += text

    def completed(_run_id: str, message: dict) -> None:
        result["events"].append("completed")
        result["completed"] = message["content"]
        app.quit()

    api.chat_items.chats_loaded.connect(chats_loaded)
    api.agent.message_accepted.connect(accepted)
    api.agent.stream_started.connect(started)
    api.agent.stream_delta.connect(delta)
    api.agent.stream_completed.connect(completed)
    api.agent.stream_failed.connect(
        lambda _run, code, detail: finish_failure(code, detail)
    )
    api.transport.request_failed.connect(finish_failure)
    QTimer.singleShot(7000, lambda: finish_failure("timeout", "round trip timed out"))
    api.chat_items.get_chat_items()
    app.exec()
    print(json.dumps(result, ensure_ascii=True))
    return 1 if failed["value"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
