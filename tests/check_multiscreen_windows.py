"""Move Navi across Windows monitors and verify stable physical size and paint."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QSize, QTimer
from PySide6.QtWidgets import QApplication

from common.config import AppConfig
from gui.window import NaviPanel, logical_size_for_screen


def main() -> int:
    app = QApplication([])
    screens = sorted(app.screens(), key=lambda screen: screen.devicePixelRatio())
    if sys.platform != "win32" or app.platformName() != "windows":
        raise RuntimeError("This check requires the Windows Qt platform.")
    if len(screens) < 2:
        print("SKIP: fewer than two monitors are connected")
        return 0

    low = screens[0]
    high = screens[-1]
    if abs(low.devicePixelRatio() - high.devicePixelRatio()) < 0.001:
        print("SKIP: connected monitors use the same scale")
        return 0

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    panel = NaviPanel(AppConfig())
    base = QSize(420, 560)
    failed = {"value": False}

    def native_size() -> QSize:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(int(panel.winId()), ctypes.byref(rect)):
            raise ctypes.WinError(ctypes.get_last_error())
        return QSize(rect.right - rect.left, rect.bottom - rect.top)

    def move_to(screen) -> None:
        area = screen.availableGeometry()
        target = logical_size_for_screen(
            base, screen.devicePixelRatio(), area.size()
        )
        panel.move(
            area.center() - QPoint(target.width() // 2, target.height() // 2)
        )

    def verify(screen, label: str) -> None:
        expected_logical = logical_size_for_screen(
            base, screen.devicePixelRatio(), screen.availableGeometry().size()
        )
        if panel.windowHandle().screen() is not screen:
            raise AssertionError(f"{label}: Qt did not switch to the target monitor")
        if panel.size() != expected_logical:
            raise AssertionError(
                f"{label}: logical size {panel.size()} != {expected_logical}"
            )
        actual_native = native_size()
        if abs(actual_native.width() - 420) > 2 or abs(actual_native.height() - 560) > 2:
            raise AssertionError(f"{label}: native size changed to {actual_native}")
        image = panel.grab().toImage()
        center = image.pixelColor(image.width() // 2, image.height() // 2)
        if center.alpha() == 0:
            raise AssertionError(f"{label}: window center became transparent")
        print(
            f"PASS: {label} dpr={screen.devicePixelRatio()} "
            f"logical={panel.width()}x{panel.height()} "
            f"native={actual_native.width()}x{actual_native.height()}"
        )

    def step_high() -> None:
        try:
            verify(low, "first monitor")
            move_to(high)
            QTimer.singleShot(700, step_back)
        except Exception:
            failed["value"] = True
            traceback.print_exc()
            panel.hide()
            app.quit()

    def step_back() -> None:
        try:
            verify(high, "second monitor")
            move_to(low)
            QTimer.singleShot(700, finish)
        except Exception:
            failed["value"] = True
            traceback.print_exc()
            panel.hide()
            app.quit()

    def finish() -> None:
        try:
            verify(low, "first monitor after return")
        except Exception:
            failed["value"] = True
            traceback.print_exc()
        finally:
            panel.hide()
            app.quit()

    panel.show()
    move_to(low)
    QTimer.singleShot(700, step_high)
    app.exec()
    return int(failed["value"])


if __name__ == "__main__":
    raise SystemExit(main())
