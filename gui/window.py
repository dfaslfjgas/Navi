import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCloseEvent, QCursor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QToolButton, QVBoxLayout, QWidget,
)

from common.config import AppConfig
from gui.chat import ChatView
from gui.api import NaviApi
from gui.history import HistorySidebar
from gui.icons import app_icon, asset_icon, make_icon
from gui.settings import SettingsDialog


POPUP_GAP = 12
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


def logical_size_for_screen(
    physical_size: QSize,
    device_pixel_ratio: float,
    available_size: QSize | None = None,
    minimum_size: QSize | None = None,
) -> QSize:
    """Choose a readable size that fits any monitor and DPI combination."""
    minimum_size = minimum_size or QSize(280, 360)
    ratio = max(float(device_pixel_ratio), 0.1)
    width = max(minimum_size.width(), round(physical_size.width() / ratio))
    height = max(minimum_size.height(), round(physical_size.height() / ratio))
    if available_size is not None:
        # Leave room for the screen edge and taskbar even on very small or
        # portrait displays. A tiny display may override the readability floor.
        usable_width = max(1, available_size.width() - 32)
        usable_height = max(1, available_size.height() - 32)
        width = min(width, usable_width)
        height = min(height, usable_height)
    return QSize(width, height)


def popup_position_near_cursor(
    cursor: QPoint, available: QRect, window_size: QSize, gap: int = POPUP_GAP
) -> QPoint:
    """Place a popup by the cursor while keeping it inside the active screen."""
    width = window_size.width()
    height = window_size.height()
    x = cursor.x() + gap
    if x + width > available.right() + 1:
        # On the right edge, the panel opens to the left of the cursor.
        x = cursor.x() - window_size.width() - gap

    centered_y = cursor.y() - height // 2
    if centered_y < available.top():
        # Near the top edge, open below the cursor.
        y = cursor.y() + gap
    elif centered_y + height > available.bottom() + 1:
        # Near the bottom edge, open above the cursor.
        y = cursor.y() - height - gap
    else:
        # In the middle of a screen, center the panel vertically on the cursor.
        y = centered_y

    max_x = max(available.left(), available.right() - window_size.width() + 1)
    max_y = max(available.top(), available.bottom() - window_size.height() + 1)
    return QPoint(
        min(max(x, available.left()), max_x),
        min(max(y, available.top()), max_y),
    )


class TitleBar(QFrame):
    def __init__(self, panel: "NaviPanel"):
        super().__init__(panel)
        self._panel = panel
        self._drag_offset: QPoint | None = None
        self.setObjectName("titleBar")
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(8)
        self.history_button = QToolButton()
        self.history_button.setObjectName("historyButton")
        self.history_button.setIcon(app_icon())
        self.history_button.setCheckable(True)
        self.history_button.setFixedSize(30, 30)
        self.history_button.setIconSize(QSize(23, 23))
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.setToolTip("展示对话")
        self.history_button.setAccessibleName("展示对话")
        self.history_button.toggled.connect(panel.set_history_visible)
        layout.addWidget(self.history_button)
        title = QLabel("Navi")
        title.setObjectName("title")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title)
        layout.addStretch()

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setIcon(asset_icon("settings.svg"))
        self.settings_button.setToolTip("设置")
        self.settings_button.setAccessibleName("设置")
        layout.addWidget(self.settings_button)

        self.pin_button = QToolButton()
        self.pin_button.setObjectName("pinButton")
        self.pin_button.setIcon(asset_icon("pin.svg"))
        self.pin_button.setCheckable(True)
        self.pin_button.setAccessibleName("置顶窗口")
        self.pin_button.setToolTip("置顶窗口")
        self.pin_button.toggled.connect(panel.set_pinned)
        self.close_button = QToolButton()
        self.close_button.setIcon(make_icon("close"))
        self.close_button.setToolTip("隐藏面板")
        self.close_button.setAccessibleName("隐藏面板")
        self.close_button.clicked.connect(panel.hide)
        for button in (self.settings_button, self.pin_button, self.close_button):
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(30, 30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(button)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._panel.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._panel.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Custom title bar deliberately has no maximize or double-click maximize.
        event.accept()


class NaviPanel(QWidget):
    message_submitted = Signal(str)

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config
        self.pinned = False
        self.api: NaviApi | None = None
        self._records: list[dict[str, str]] = []
        self._loaded_messages: list[dict] = []
        self._active_chat_id: str | None = None
        self._chat_has_more = False
        self._chat_loading = False
        self._message_has_more = False
        self._message_loading = False
        self._busy_chats: set[str] = set()
        self._run_chats: dict[str, str] = {}
        self._pending_send_chat_id: str | None = None
        self._placing_history = False
        self._screen_signal_connected = False
        self._screen_sync_pending = False
        self._current_dpr = 1.0
        self.settings_dialog: SettingsDialog | None = None
        self.setObjectName("naviPanel")
        self.setWindowTitle(config.app_name)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(config.panel_width, config.panel_height)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)
        self.surface = QFrame()
        self.surface.setObjectName("panelSurface")
        self._install_surface_shadow(1.0)
        root.addWidget(self.surface)
        surface_layout = QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        self.title_bar.settings_button.clicked.connect(self._open_settings)
        surface_layout.addWidget(self.title_bar)
        self.history = HistorySidebar(self)
        self.history.hide()
        self.history.refresh_requested.connect(self.refresh_items)
        self.history.new_requested.connect(self._new_conversation)
        self.history.conversation_selected.connect(self._open_conversation)
        self.history.rename_requested.connect(self._rename_conversation)
        self.history.delete_requested.connect(self._delete_conversation)
        self.history.load_more_requested.connect(self.load_more_chats)

        self.chat = ChatView()
        self.content = self.chat
        self.chat.message_submitted.connect(self._record_message)
        self.chat.input.escape_requested.connect(self.hide)
        self.chat.load_older_requested.connect(self.load_more_content)
        self.chat.set_chat_available(False)
        surface_layout.addWidget(self.chat, 1)
        self.setStyleSheet("""
            QWidget#naviPanel { background: transparent; }
            QFrame#panelSurface { background: #ffffff; border: 1px solid #dce1e9; border-radius: 12px; }
            QFrame#titleBar { background: #f7f8fc; border-bottom: 1px solid #e7eaf0;
                border-top-left-radius: 12px; border-top-right-radius: 12px; }
            QLabel#title { color: #283044; font-size: 14px; font-weight: 600; }
            QWidget#chatView, QWidget#messagePage { background: #f9fafc; }
            QScrollArea#messageScroll { background: #f9fafc; border: none; }
            QWidget#welcome { background: transparent; }
            QLabel#welcomeMark {
                background: transparent; border: none;
            }
            QLabel#welcomeTitle { color: #232b3d; font-size: 18px; font-weight: 650; }
            QLabel#welcomeSubtitle { color: #8a93a5; font-size: 12px; }
            QFrame#userBubble { background: #5268e8; border: none; border-radius: 13px; }
            QFrame#assistantBubble { background: #ffffff; border: 1px solid #e3e7ef; border-radius: 13px; }
            QFrame#userBubble QLabel#messageText { color: #ffffff; font-size: 13px; }
            QFrame#assistantBubble QLabel#messageText { color: #293044; font-size: 13px; }
            QWidget#composerArea { background: #ffffff; border-top: 1px solid #e7eaf0; }
            QFrame#composer { background: #ffffff; border: 1px solid #d8deea; border-radius: 13px; }
            QTextEdit#chatInput {
                color: #252c3c; background: transparent; border: none;
                selection-background-color: #ccd4ff; font-size: 13px;
            }
            QLabel#inputHint { color: #9aa2b1; font-size: 10px; }
            QToolButton { border: none; border-radius: 6px; background: transparent; }
            QToolButton:hover { background: #e9ecf4; }
            QToolButton:checked { background: #e2e7ff; }
            QToolButton:focus { border: 1px solid #5268e8; }
            QToolButton#historyButton:checked { background: #e2e7ff; }
            QToolButton#sendButton { background: #5268e8; border-radius: 10px; }
            QToolButton#sendButton:hover { background: #4359dc; }
            QToolButton#sendButton:pressed { background: #354bc9; }
            QToolButton#sendButton:disabled { background: #cbd1dd; }
            QToolButton#loadMoreButton { color: #5268e8; background: transparent; padding: 5px; }
        """)

    def show_panel(self) -> None:
        cursor = QCursor.pos()
        screens = QApplication.screens()
        screen = QApplication.screenAt(cursor)
        if screen is None and screens:
            # Cursor may briefly lie between displays in a nonrectangular layout.
            screen = min(
                screens,
                key=lambda candidate: (
                    max(candidate.geometry().left() - cursor.x(), 0, cursor.x() - candidate.geometry().right()) ** 2
                    + max(candidate.geometry().top() - cursor.y(), 0, cursor.y() - candidate.geometry().bottom()) ** 2
                ),
            )
        if screen is not None:
            self._apply_screen_metrics(screen, clamp_position=False)
            self.move(
                popup_position_near_cursor(
                    cursor,
                    screen.availableGeometry(),
                    self.size(),
                )
            )
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.chat.focus_input()
        if self.title_bar.history_button.isChecked():
            self._show_history()
        if sys.platform == "win32" and QApplication.platformName() == "windows":
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.SetForegroundWindow.restype = wintypes.BOOL
            user32.SetForegroundWindow(int(self.winId()))

    def _install_surface_shadow(self, device_pixel_ratio: float) -> None:
        ratio = max(float(device_pixel_ratio), 0.1)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(28 / ratio)
        shadow.setOffset(0, 4 / ratio)
        shadow.setColor(QColor(18, 28, 48, 80))
        self.surface.setGraphicsEffect(shadow)

    def _connect_screen_signal(self) -> None:
        if self._screen_signal_connected:
            return
        handle = self.windowHandle()
        if handle is None:
            return
        handle.screenChanged.connect(self._schedule_screen_sync)
        self._screen_signal_connected = True

    def _schedule_screen_sync(self, screen=None) -> None:
        if getattr(self, "_screen_sync_pending", False):
            return
        self._screen_sync_pending = True

        def apply() -> None:
            self._screen_sync_pending = False
            handle = self.windowHandle()
            active_screen = screen or (handle.screen() if handle else None)
            if active_screen is not None:
                self._apply_screen_metrics(active_screen)

        # WM_DPICHANGED and Qt's backing-store update finish asynchronously.
        QTimer.singleShot(0, lambda: QTimer.singleShot(0, apply))

    def _apply_screen_metrics(self, screen, *, clamp_position: bool = True) -> None:
        ratio = max(float(screen.devicePixelRatio()), 0.1)
        available = screen.availableGeometry()
        target = logical_size_for_screen(
            QSize(self._config.panel_width, self._config.panel_height),
            ratio,
            available.size(),
        )
        ratio_changed = abs(ratio - self._current_dpr) > 0.001
        if self.size() != target:
            self.setFixedSize(target)
        self._current_dpr = ratio
        self.history.apply_screen_scale(ratio, target.height())
        if ratio_changed:
            # QGraphicsEffect caches a device-pixel pixmap. Recreate it after a
            # per-monitor DPI change so a translucent window cannot go blank.
            self._install_surface_shadow(ratio)
            self.surface.updateGeometry()
            if self.layout() is not None:
                self.layout().activate()
            self.surface.update()
            self.update()
        if clamp_position:
            area = available
            max_x = max(area.left(), area.right() - self.width() + 1)
            max_y = max(area.top(), area.bottom() - self.height() + 1)
            position = QPoint(
                min(max(self.x(), area.left()), max_x),
                min(max(self.y(), area.top()), max_y),
            )
            if position != self.pos():
                self.move(position)
        if self.history.isVisible():
            self._place_history()
        QTimer.singleShot(0, self.repaint)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._connect_screen_signal()
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not None:
            self._apply_screen_metrics(handle.screen(), clamp_position=False)

    def event(self, event) -> bool:
        result = super().event(event)
        if event.type() in {
            QEvent.Type.ScreenChangeInternal,
            QEvent.Type.DevicePixelRatioChange,
        }:
            self._schedule_screen_sync()
        return result

    def set_pinned(self, pinned: bool) -> None:
        if self.pinned == pinned:
            return
        self.pinned = pinned
        geometry = self.geometry()
        was_visible = self.isVisible()
        native_updated = self._set_native_topmost(pinned)
        if not native_updated:
            # Non-Windows fallback: changing this Qt flag recreates the window.
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
            self.setGeometry(geometry)
        button = self.title_bar.pin_button
        button.blockSignals(True)
        button.setChecked(pinned)
        button.blockSignals(False)
        button.setToolTip("取消置顶" if pinned else "置顶窗口")
        button.setAccessibleName(button.toolTip())
        if was_visible and not native_updated:
            self.showNormal()
            self.raise_()

    def set_history_visible(self, visible: bool) -> None:
        button = self.title_bar.history_button
        label = "隐藏对话" if visible else "展示对话"
        button.setToolTip(label)
        button.setAccessibleName(label)
        if visible and self.isVisible():
            self._show_history()
            self.refresh_items()
        else:
            self.history.hide()

    def _record_message(self, message: str) -> None:
        if self.api is None or self._active_chat_id is None:
            self.chat.set_sending(False)
            self.history.status.setText("请先新建或选择一个对话")
            return
        chat_id = self._active_chat_id
        self._busy_chats.add(chat_id)
        self._pending_send_chat_id = chat_id
        self.history.status.setText("正在发送消息…")
        self.api.agent.send_message(chat_id, message)
        self.message_submitted.emit(message)

    def add_assistant_message(self, message: str) -> None:
        self.chat.add_message(message, "assistant")

    def attach_api(self, api: NaviApi) -> None:
        self.api = api
        api.chat_items.chats_loaded.connect(self._on_chats_loaded)
        api.chat_content.messages_loaded.connect(self._on_messages_loaded)
        api.chat_items.chat_created.connect(self._on_chat_created)
        api.chat_items.chat_renamed.connect(self._on_chat_renamed)
        api.chat_items.chat_deleted.connect(self._on_chat_deleted)
        api.agent.message_accepted.connect(self._on_message_accepted)
        api.agent.stream_started.connect(self._on_stream_started)
        api.agent.stream_delta.connect(self._on_stream_delta)
        api.agent.stream_completed.connect(self._on_stream_completed)
        api.agent.stream_failed.connect(self._on_stream_failed)
        api.transport.request_failed.connect(self._on_request_failed)

    def _open_settings(self) -> None:
        """打开模型配置窗口，并在每次展示时刷新后端数据。"""
        if self.api is None:
            return
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.api, self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
        self.settings_dialog.refresh()

    def refresh_items(self) -> None:
        if self.api is None:
            self.history.status.setText("尚未连接 Agent")
            return
        self._chat_loading = True
        self.history.set_paging(self._chat_has_more, True)
        self.history.status.setText("正在加载对话…")
        self.api.chat_items.get_chat_items()

    def load_more_chats(self) -> None:
        if (
            self.api is None or self._chat_loading or not self._chat_has_more
            or not self._records
        ):
            return
        before = self._records[-1].get("activity_time")
        if not before:
            return
        self._chat_loading = True
        self.history.set_paging(True, True)
        self.api.chat_items.get_chat_items(before)

    def _on_chats_loaded(self, records: list[dict], has_more: bool, is_more: bool) -> None:
        self._chat_loading = False
        self._chat_has_more = has_more
        if is_more:
            known = {item["id"] for item in self._records}
            additions = [item for item in records if item["id"] not in known]
            self._records.extend(additions)
            self.history.append_items(additions, self._active_chat_id)
        else:
            self._records = records
            self.history.set_items(records, self._active_chat_id)
        self.history.set_paging(has_more, False)

    def _new_conversation(self) -> None:
        if self.api is None:
            self.history.status.setText("尚未连接 Agent")
            return
        self.history.status.setText("正在创建对话…")
        self.api.chat_items.create_chat_item()

    def _on_chat_created(self, record: dict) -> None:
        self._records.insert(0, record)
        self._active_chat_id = str(record["id"])
        self._loaded_messages = []
        self._message_has_more = False
        self.history.set_items(self._records, self._active_chat_id)
        self.chat.clear_messages()
        self.chat.input.clear()
        self.chat.set_chat_available(True)
        self.chat.set_sending(False)
        self.chat.set_history_paging(False, False)
        self.chat.focus_input()

    def _open_conversation(self, chat_id: str) -> None:
        if chat_id == self._active_chat_id:
            return
        self._active_chat_id = chat_id
        self._loaded_messages = []
        self._message_has_more = False
        self._message_loading = True
        self.history.select_chat(chat_id)
        self.chat.clear_messages()
        self.chat.input.clear()
        self.chat.set_chat_available(True)
        self.chat.set_sending(chat_id in self._busy_chats)
        self.chat.set_history_paging(False, True)
        self.chat.focus_input()
        if self.api is not None:
            self.history.status.setText("正在加载内容…")
            self.api.chat_content.get_chat_content(chat_id)

    def load_more_content(self) -> None:
        if (
            self.api is None or self._active_chat_id is None or self._message_loading
            or not self._message_has_more or not self.chat.messages
        ):
            return
        before = next(
            (message.get("created_time") for message in self._loaded_messages if message.get("created_time")),
            None,
        )
        if not before:
            return
        self._message_loading = True
        self.chat.set_history_paging(True, True)
        self.api.chat_content.get_chat_content(self._active_chat_id, before)

    def _on_messages_loaded(
        self, chat_id: str, messages: list[dict], has_more: bool, is_older: bool
    ) -> None:
        if chat_id != self._active_chat_id:
            return
        self._message_loading = False
        self._message_has_more = has_more
        if is_older:
            known = {item["id"] for item in self._loaded_messages}
            additions = [item for item in messages if item["id"] not in known]
            self._loaded_messages = additions + self._loaded_messages
            self.chat.prepend_messages(additions)
        else:
            self._loaded_messages = messages
            for message in messages:
                self.chat.add_message(
                    message["content"], message["role"], message["id"], scroll=False
                )
            self.chat.finish_initial_load(has_more)
        if is_older:
            self.chat.set_history_paging(has_more, False)
        self.history.status.setText(f"已加载 {len(self.chat.messages)} 条消息")

    def _rename_conversation(self, chat_id: str) -> None:
        record = next((item for item in self._records if item["id"] == chat_id), None)
        if record is None or self.api is None:
            return
        name, accepted = QInputDialog.getText(self, "重命名对话", "对话名称：", text=record["name"])
        name = name.strip()
        if accepted and name and name != record["name"]:
            self.api.chat_items.rename_chat_item(chat_id, name)

    def _on_chat_renamed(self, updated: dict) -> None:
        for record in self._records:
            if record["id"] == str(updated["id"]):
                record.update(updated)
        self.history.set_items(self._records, self._active_chat_id)

    def _delete_conversation(self, chat_id: str) -> None:
        record = next((item for item in self._records if item["id"] == chat_id), None)
        if record is None or self.api is None:
            return
        answer = QMessageBox.question(
            self, "删除对话", f"确定删除「{record['name']}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.api.chat_items.delete_chat_item(chat_id)

    def _on_chat_deleted(self, chat_id: str) -> None:
        self._records = [item for item in self._records if item["id"] != chat_id]
        if chat_id == self._active_chat_id:
            self._active_chat_id = None
            self._loaded_messages = []
            self.chat.clear_messages()
            self.chat.set_chat_available(False)
            self.chat.set_sending(False)
        self.history.set_items(self._records, self._active_chat_id)

    def _on_message_accepted(self, chat_id: str, run_id: str, message: dict) -> None:
        self._pending_send_chat_id = None
        self._run_chats[run_id] = chat_id
        if chat_id == self._active_chat_id:
            normalized = {
                "id": str(message["id"]), "role": "user",
                "content": str(message.get("content") or ""),
                "status": str(message.get("status") or "completed"),
                "created_time": str(message.get("created_time") or ""),
            }
            self._loaded_messages.append(normalized)
            self.chat.accept_user_message(normalized)
            self.history.status.setText("Navi 正在回复…")

    def _on_stream_started(self, run_id: str, message_id: str) -> None:
        if self._run_chats.get(run_id) == self._active_chat_id:
            self.chat.start_assistant_message(message_id)

    def _on_stream_delta(self, run_id: str, message_id: str, delta: str) -> None:
        if self._run_chats.get(run_id) == self._active_chat_id:
            self.chat.append_assistant_delta(message_id, delta)

    def _finish_run(self, run_id: str) -> str | None:
        chat_id = self._run_chats.pop(run_id, None)
        if chat_id:
            self._busy_chats.discard(chat_id)
        if chat_id == self._active_chat_id:
            self.chat.set_sending(False)
        return chat_id

    def _on_stream_completed(self, run_id: str, message: dict) -> None:
        chat_id = self._run_chats.get(run_id)
        if chat_id == self._active_chat_id:
            self.chat.finish_assistant_message(message)
            self.history.status.setText("回复完成")
        self._finish_run(run_id)

    def _on_stream_failed(self, run_id: str, code: str, detail: str) -> None:
        chat_id = self._finish_run(run_id)
        if chat_id == self._active_chat_id:
            self.history.status.setText(f"回复失败：{code}: {detail}")

    def _on_request_failed(self, operation: str, detail: str) -> None:
        if operation == "send_message" and self._pending_send_chat_id:
            chat_id = self._pending_send_chat_id
            self._pending_send_chat_id = None
            self._busy_chats.discard(chat_id)
            if chat_id == self._active_chat_id:
                self.chat.set_sending(False)
        self.history.status.setText(f"{operation} 失败：{detail}（可刷新重试）")

    def _show_history(self) -> None:
        self.history.setFixedHeight(self.height())
        self._place_history()
        self.history.show()
        self.history.raise_()

    def _place_history(self) -> None:
        if self._placing_history:
            return
        self._placing_history = True
        try:
            screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            overlap = 18  # transparent shadow margins overlap; painted surfaces stay separate
            left = self.x() - self.history.width() + overlap
            if left < area.left():
                shift = area.left() - left
                if self.x() + shift + self.width() <= area.right() + 1:
                    self.move(self.x() + shift, self.y())
                    left = area.left()
                else:
                    left = area.left()
            self.history.move(left, self.y())
        finally:
            self._placing_history = False

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.history.isVisible():
            self._place_history()

    def hideEvent(self, event) -> None:
        self.history.hide()
        super().hideEvent(event)

    def _set_native_topmost(self, pinned: bool) -> bool:
        """Toggle Win32 topmost state without hiding or recreating the window."""
        if sys.platform != "win32" or QApplication.platformName() != "windows":
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        insert_after = HWND_TOPMOST if pinned else HWND_NOTOPMOST
        return bool(
            user32.SetWindowPos(
                int(self.winId()),
                insert_after,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)
