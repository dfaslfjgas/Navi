"""Windows global hotkey registered on the GUI thread, without keyboard hooks."""

import ctypes
from ctypes import wintypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
HOTKEY_ID = 0x4E41
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, app: QApplication, callback: Callable[[], None]):
        super().__init__()
        self._app = app
        self._callback = callback
        self._registered = False
        self._user32 = None

    def start(self) -> None:
        if self._registered:
            return
        if sys.platform != "win32":
            raise RuntimeError("当前版本的全局快捷键仅支持 Windows。")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT
        ]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        # NULL HWND ties registration to the GUI thread instead of the panel HWND.
        # Changing WindowStaysOnTopHint recreates the panel HWND, not this registration.
        if not self._user32.RegisterHotKey(
            None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("K")
        ):
            error = ctypes.get_last_error()
            raise OSError(error, "Ctrl+Shift+K 注册失败，可能已被其他应用占用。")
        self._registered = True
        self._app.installNativeEventFilter(self)

    def stop(self) -> None:
        if self._registered:
            self._app.removeNativeEventFilter(self)
            self._user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def nativeEventFilter(self, event_type, message):
        if self._registered and bytes(event_type) in (
            b"windows_generic_MSG", b"windows_dispatcher_MSG"
        ):
            native = wintypes.MSG.from_address(int(message))
            if native.message == WM_HOTKEY and native.wParam == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0
