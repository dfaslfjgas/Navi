from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from gui.icons import app_icon


class NaviTray(QObject):
    def __init__(self, show_panel: Callable[[], None], quit_app: Callable[[], None]):
        super().__init__()
        self._show_panel = show_panel
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("Navi · Ctrl+Shift+K")
        self.menu = QMenu()
        self.show_action = QAction("显示面板  Ctrl+Shift+K", self)
        self.show_action.triggered.connect(show_panel)
        self.menu.addAction(self.show_action)
        self.menu.addSeparator()
        self.quit_action = QAction("退出 Navi", self)
        self.quit_action.triggered.connect(quit_app)
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_panel()

    def show(self) -> None:
        self.icon.show()

    def stop(self) -> None:
        self.icon.hide()

    def report_hotkey_error(self, detail: str) -> None:
        self.icon.setToolTip("Navi · 快捷键不可用，点击显示面板")
        self.show_action.setText("显示面板")
        status = QAction("Ctrl+Shift+K 不可用（可能已被占用）", self)
        status.setEnabled(False)
        self.menu.insertAction(self.show_action, status)
        self.icon.showMessage(
            "Navi 快捷键不可用", detail,
            QSystemTrayIcon.MessageIcon.Warning, 6000,
        )
