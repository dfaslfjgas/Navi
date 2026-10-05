"""Floating conversation list shown to the left of the chat panel."""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMenu, QToolButton, QVBoxLayout, QWidget,
)

from gui.icons import asset_icon


class ConversationRow(QFrame):
    selected = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, record: dict[str, str]):
        super().__init__()
        self.record = record
        self.setObjectName("conversationRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(2)
        self.title = QLabel(record["name"])
        self.title.setObjectName("conversationTitle")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.title, 1)
        self.more = QToolButton()
        self.more.setObjectName("moreButton")
        self.more.setIcon(asset_icon("more-horizontal.svg"))
        self.more.setIconSize(QSize(18, 18))
        self.more.setFixedSize(26, 26)
        self.more.setToolTip("更多操作")
        self.more.setAccessibleName("更多操作")
        self.menu = QMenu(self)
        self.menu.addAction("重命名", lambda: self.rename_requested.emit(self.record["id"]))
        self.menu.addAction("删除", lambda: self.delete_requested.emit(self.record["id"]))
        self.more.setMenu(self.menu)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        layout.addWidget(self.more)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.record["id"])
        super().mousePressEvent(event)


class HistorySidebar(QWidget):
    refresh_requested = Signal()
    new_requested = Signal()
    conversation_selected = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    load_more_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("historySidebar")
        self._base_width = 240
        self._current_dpr = 1.0
        self.setFixedWidth(self._base_width)
        self._has_more = False
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.surface = QFrame()
        self.surface.setObjectName("historySurface")
        self._install_shadow(1.0)
        outer.addWidget(self.surface)

        layout = QVBoxLayout(self.surface)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        heading = QLabel("对话")
        heading.setObjectName("historyHeading")
        header.addWidget(heading)
        header.addStretch()
        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setIcon(asset_icon("refresh.svg"))
        self.refresh_button.setIconSize(QSize(19, 19))
        self.refresh_button.setFixedSize(28, 28)
        self.refresh_button.setToolTip("刷新对话")
        self.refresh_button.setAccessibleName("刷新对话")
        self.refresh_button.clicked.connect(self.refresh_requested)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.new_button = QToolButton()
        self.new_button.setObjectName("newConversationButton")
        self.new_button.setText("＋  新对话")
        self.new_button.setToolTip("新对话")
        self.new_button.clicked.connect(self.new_requested)
        layout.addWidget(self.new_button)

        self.list = QListWidget()
        self.list.setObjectName("conversationList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        layout.addWidget(self.list, 1)

        self.status = QLabel("点击刷新获取对话")
        self.status.setObjectName("historyStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setStyleSheet("""
            QFrame#historySurface { background: #f5f7fb; border: 1px solid #dfe3eb; border-radius: 12px; }
            QLabel#historyHeading { color: #4e596c; font-size: 13px; font-weight: 600; }
            QLabel#historyStatus { color: #80899b; font-size: 11px; }
            QListWidget#conversationList { background: transparent; border: none; }
            QListWidget#conversationList::item { border-radius: 7px; }
            QListWidget#conversationList::item:selected { background: #e0e6f8; }
            QFrame#conversationRow { background: transparent; border: none; }
            QLabel#conversationTitle { color: #3e4859; font-size: 12px; }
            QToolButton#newConversationButton {
                background: #ffffff; border: 1px solid #dfe3ec; border-radius: 8px;
                color: #384257; text-align: left; padding: 7px;
            }
            QToolButton#refreshButton, QToolButton#moreButton { border: none; background: transparent; border-radius: 6px; }
            QToolButton#refreshButton:hover, QToolButton#moreButton:hover { background: #e5eaf4; }
        """)

    def set_items(self, records: list[dict[str, str]], selected_chat_id: str | None = None) -> None:
        self.list.clear()
        for record in records:
            self._add_item(record, selected_chat_id)
        self.status.setText(f"共 {len(records)} 个对话" if records else "暂无对话")

    def _install_shadow(self, device_pixel_ratio: float) -> None:
        ratio = max(float(device_pixel_ratio), 0.1)
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(26 / ratio)
        shadow.setOffset(0, 3 / ratio)
        shadow.setColor(QColor(15, 25, 50, 80))
        self.surface.setGraphicsEffect(shadow)

    def apply_screen_scale(self, device_pixel_ratio: float, panel_height: int) -> None:
        ratio = max(float(device_pixel_ratio), 0.1)
        self.setFixedSize(max(180, round(self._base_width / ratio)), panel_height)
        if abs(ratio - self._current_dpr) > 0.001:
            self._current_dpr = ratio
            self._install_shadow(ratio)
            self.surface.updateGeometry()
            self.surface.update()
            self.update()

    def append_items(self, records: list[dict[str, str]], selected_chat_id: str | None = None) -> None:
        for record in records:
            self._add_item(record, selected_chat_id)
        self.status.setText(f"已加载 {self.list.count()} 个对话")

    def _add_item(self, record: dict[str, str], selected_chat_id: str | None) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, record["id"])
        item.setSizeHint(QSize(190, 38))
        self.list.addItem(item)
        row = ConversationRow(record)
        row.selected.connect(self.conversation_selected)
        row.rename_requested.connect(self.rename_requested)
        row.delete_requested.connect(self.delete_requested)
        self.list.setItemWidget(item, row)
        if record["id"] == selected_chat_id:
            self.list.setCurrentItem(item)

    def set_paging(self, has_more: bool, loading: bool) -> None:
        self._has_more = has_more
        self._loading = loading

    def _on_scroll(self, value: int) -> None:
        bar = self.list.verticalScrollBar()
        if value >= bar.maximum() - 40 and self._has_more and not self._loading:
            self.load_more_requested.emit()

    def select_chat(self, chat_id: str) -> None:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == chat_id:
                self.list.setCurrentItem(item)
                return
