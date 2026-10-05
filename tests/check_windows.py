"""Native Windows smoke check. Owns and cleans up only its own Navi objects."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from common.config import AppConfig
from gui.hotkey import HOTKEY_ID, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT, WM_HOTKEY
from gui.main import GuiController


def main() -> int:
    if sys.platform != "win32":
        raise RuntimeError("This smoke check requires Windows.")
    app = QApplication([])
    if app.platformName() != "windows" or not QSystemTrayIcon.isSystemTrayAvailable():
        raise RuntimeError("A real Windows desktop with a system tray is required.")
    controller = GuiController(app, AppConfig())
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    thread_id = kernel32.GetCurrentThreadId()
    modifiers = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    status = {"failed": False}

    def check(condition: bool, description: str) -> None:
        if not condition:
            raise AssertionError(description)
        print(f"PASS: {description}", flush=True)

    def post_hotkey() -> None:
        check(bool(user32.PostThreadMessageW(thread_id, WM_HOTKEY, HOTKEY_ID, (ord("K") << 16) | (MOD_CONTROL | MOD_SHIFT))), "system hotkey message posted")

    def begin() -> None:
        check(controller.tray.icon.isVisible(), "tray icon active")
        check(not controller.panel.isVisible(), "panel hidden at startup")
        check(controller.hotkey._registered, "Windows global hotkey registered")
        # A second ID cannot claim the same chord while Navi owns it.
        duplicate = user32.RegisterHotKey(None, HOTKEY_ID + 1, modifiers, ord("K"))
        if duplicate:
            user32.UnregisterHotKey(None, HOTKEY_ID + 1)
        check(not duplicate, "Windows confirms exclusive hotkey ownership")
        post_hotkey()

    def shown() -> None:
        panel = controller.panel
        check(panel.isVisible(), "native dispatcher message displays panel")
        check(not (user32.GetWindowLongW(int(panel.winId()), -16) & 0x00010000), "native maximize box absent")
        check(panel.minimumSize() == panel.maximumSize(), "panel size fixed")
        panel.title_bar.pin_button.click()
        check(bool(user32.GetWindowLongW(int(panel.winId()), -20) & 0x00000008), "native WS_EX_TOPMOST enabled")

    def pinned() -> None:
        panel = controller.panel
        preview = Path(__file__).resolve().parents[1] / "navi-preview.png"
        check(panel.grab().save(str(preview)), "panel screenshot saved")
        panel.close()
        check(not panel.isVisible(), "close hides panel")
        post_hotkey()

    def reopened() -> None:
        panel = controller.panel
        check(panel.isVisible() and panel.pinned, "hotkey works after HWND recreation and hide")
        panel.title_bar.pin_button.click()
        check(not (user32.GetWindowLongW(int(panel.winId()), -20) & 0x00000008), "native WS_EX_TOPMOST cleared")
        controller.stop()
        check(not controller.tray.icon.isVisible(), "tray icon removed on exit")
        available = user32.RegisterHotKey(None, HOTKEY_ID + 1, modifiers, ord("K"))
        try:
            check(bool(available), "hotkey available again after cleanup")
        finally:
            if available:
                user32.UnregisterHotKey(None, HOTKEY_ID + 1)
        app.quit()

    def guarded(step) -> None:
        try:
            step()
        except Exception:
            status["failed"] = True
            traceback.print_exc()
            controller.stop()
            app.quit()

    controller.start()
    for delay, step in ((300, begin), (700, shown), (1100, pinned), (1500, reopened)):
        QTimer.singleShot(delay, lambda callback=step: guarded(callback))
    try:
        app.exec()
    finally:
        controller.stop()
    return int(status["failed"])


if __name__ == "__main__":
    raise SystemExit(main())
