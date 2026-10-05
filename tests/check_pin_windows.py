"""Check Pin on a real Windows desktop without registering the global hotkey."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from common.config import AppConfig
from gui.window import NaviPanel


WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20


def main() -> int:
    app = QApplication([])
    if sys.platform != "win32" or app.platformName() != "windows":
        raise RuntimeError("This check requires the Windows Qt platform.")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    panel = NaviPanel(AppConfig())
    failed = False
    panel.show_panel()
    handle = int(panel.winId())
    position = panel.pos()

    def verify() -> None:
        nonlocal failed
        try:
            assert panel.isVisible()
            assert panel.surface.graphicsEffect() is not None, "main shadow missing"
            panel.title_bar.history_button.click()
            assert panel.history.isVisible(), "history sidebar did not open"
            assert panel.history.surface.graphicsEffect() is not None, "history shadow missing"
            assert int(panel.history.winId()) != handle, "history is not an independent window"
            assert panel.history.x() < panel.x(), "history did not open to the left"
            assert panel.width() == 420, "history changed the chat panel width"
            panel.title_bar.history_button.click()
            assert not panel.history.isVisible(), "history did not close"
            assert not user32.GetWindowLongW(handle, GWL_EXSTYLE) & WS_EX_TOPMOST
            panel.title_bar.pin_button.click()
            assert panel.pinned
            assert panel.isVisible()
            assert int(panel.winId()) == handle, "Pin recreated the window"
            assert panel.pos() == position, "Pin moved the window"
            assert user32.GetWindowLongW(handle, GWL_EXSTYLE) & WS_EX_TOPMOST
            panel.title_bar.pin_button.click()
            assert not panel.pinned
            assert panel.isVisible()
            assert int(panel.winId()) == handle, "Unpin recreated the window"
            assert panel.pos() == position, "Unpin moved the window"
            assert not user32.GetWindowLongW(handle, GWL_EXSTYLE) & WS_EX_TOPMOST
            print("PASS: separate shadowed sidebar and unchanged chat panel width")
            print("PASS: Pin toggled native topmost state without recreating or moving the visible window")
        except Exception:
            failed = True
            traceback.print_exc()
        finally:
            panel.hide()
            app.quit()

    QTimer.singleShot(200, verify)
    app.exec()
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
