import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from common.config import AppConfig
from gui.api import NaviApi
from gui.hotkey import GlobalHotkey
from gui.icons import app_icon
from gui.tray import NaviTray
from gui.window import NaviPanel


class GuiController:
    """Own all long-lived GUI objects and clean up OS registrations on exit."""

    def __init__(self, app: QApplication, config: AppConfig):
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.api = NaviApi(config.agent_base_url)
        self.panel = NaviPanel(config)
        self.panel.attach_api(self.api)
        self.tray = NaviTray(self.panel.show_panel, self.app.quit)
        self.hotkey = GlobalHotkey(app, self.panel.show_panel)
        self._stopped = False
        self.app.aboutToQuit.connect(self.stop)

    def start(self) -> None:
        self.tray.show()
        try:
            self.hotkey.start()
        except (OSError, RuntimeError) as error:
            logging.warning("Global hotkey unavailable: %s", error)
            self.tray.report_hotkey_error(str(error))

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.hotkey.stop()
        self.tray.stop()
        self.panel.hide()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Navi")
    app.setOrganizationName("Navi")
    app.setWindowIcon(app_icon())
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Navi 无法启动", "当前桌面没有可用的系统托盘。")
        return 1
    controller = GuiController(app, AppConfig())
    controller.start()
    try:
        return app.exec()
    finally:
        controller.stop()
