"""Chat widgets. This module contains presentation state only, not agent logic."""

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.icons import app_icon, make_icon


class ChatInput(QTextEdit):
    """Multiline input where Enter submits and Shift+Enter inserts a newline."""

    submitted = Signal()
    escape_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_requested.emit()
            event.accept()
            return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MessageBubble(QFrame):
    def __init__(self, text: str, role: str, message_id: str | None = None):
        super().__init__()
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")
        self.role = role
        self.message_id = message_id
        self.setObjectName("userBubble" if role == "user" else "assistantBubble")
        self.setMaximumWidth(292)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 9)
        label = QLabel(text)
        label.setObjectName("messageText")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(label)
        self.label = label

    def set_text(self, text: str) -> None:
        self.label.setText(text)

    def append_text(self, delta: str) -> None:
        self.label.setText(self.label.text() + delta)


class ChatView(QWidget):
    """Conversation history and composer presentation state."""

    message_submitted = Signal(str)
    load_older_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("chatView")
        self.messages: list[MessageBubble] = []
        self._rows: list[QWidget] = []
        self._message_by_id: dict[str, MessageBubble] = {}
        self._sending = False
        self._chat_available = False
        self._history_has_more = False
        self._history_loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("messageScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.message_page = QWidget()
        self.message_page.setObjectName("messagePage")
        self.message_layout = QVBoxLayout(self.message_page)
        self.message_layout.setContentsMargins(18, 22, 18, 14)
        self.message_layout.setSpacing(12)

        self.welcome = self._build_welcome()
        self.message_layout.addStretch(1)
        self.message_layout.addWidget(self.welcome, 0, Qt.AlignmentFlag.AlignHCenter)
        self.message_layout.addStretch(2)
        self.scroll.setWidget(self.message_page)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.scroll, 1)

        composer_area = QWidget()
        composer_area.setObjectName("composerArea")
        composer_layout = QVBoxLayout(composer_area)
        composer_layout.setContentsMargins(14, 8, 14, 12)
        composer_layout.setSpacing(6)

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        input_layout = QHBoxLayout(self.composer)
        input_layout.setContentsMargins(12, 8, 8, 8)
        input_layout.setSpacing(8)

        self.input = ChatInput()
        self.input.setObjectName("chatInput")
        self.input.setPlaceholderText("给 Navi 发送消息…")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(54)
        self.input.setTabChangesFocus(True)
        self.input.setAccessibleName("消息输入框")
        input_layout.addWidget(self.input, 1)

        self.send_button = QToolButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setIcon(make_icon("send", "#ffffff"))
        self.send_button.setFixedSize(36, 36)
        self.send_button.setToolTip("发送消息")
        self.send_button.setAccessibleName("发送消息")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setEnabled(False)
        input_layout.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)

        hint = QLabel("Enter 发送  ·  Shift+Enter 换行")
        hint.setObjectName("inputHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        composer_layout.addWidget(self.composer)
        composer_layout.addWidget(hint)
        root.addWidget(composer_area)

        self.input.textChanged.connect(self._update_send_state)
        self.input.submitted.connect(self.submit)
        self.send_button.clicked.connect(self.submit)

    def _build_welcome(self) -> QWidget:
        welcome = QWidget()
        welcome.setObjectName("welcome")
        layout = QVBoxLayout(welcome)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        mark = QLabel()
        mark.setObjectName("welcomeMark")
        mark.setFixedSize(46, 46)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(app_icon().pixmap(QSize(42, 42)))
        mark.setAccessibleName("Navi 小狗图标")
        self.welcome_mark = mark
        title = QLabel("有什么可以帮你？")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("输入消息，开始与 Navi 对话")
        subtitle.setObjectName("welcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return welcome

    def _update_send_state(self) -> None:
        self.send_button.setEnabled(
            self._chat_available
            and not self._sending
            and bool(self.input.toPlainText().strip())
        )

    def submit(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or not self._chat_available or self._sending:
            return
        self.set_sending(True)
        self.message_submitted.emit(text)

    def add_message(
        self,
        text: str,
        role: str,
        message_id: str | None = None,
        *,
        prepend: bool = False,
        scroll: bool = True,
    ) -> MessageBubble:
        if not self.messages:
            self._remove_welcome_state()
        display_role = "assistant" if role == "system" else role
        bubble = MessageBubble(text, display_role, message_id)
        row = QWidget()
        row.setObjectName("messageRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if display_role == "user":
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch()
        if prepend:
            # Index 0 is the expanding spacer that keeps short conversations
            # aligned to the bottom. Older messages go directly after it.
            self.message_layout.insertWidget(1, row)
            self.messages.insert(0, bubble)
            self._rows.insert(0, row)
        else:
            # Append after the top spacer so new messages remain at the bottom.
            self.message_layout.insertWidget(self.message_layout.count(), row)
            self.messages.append(bubble)
            self._rows.append(row)
        if message_id:
            self._message_by_id[message_id] = bubble
        if scroll:
            QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def prepend_messages(self, messages: list[dict]) -> None:
        bar = self.scroll.verticalScrollBar()
        old_value = bar.value()
        old_maximum = bar.maximum()
        for message in reversed(messages):
            self.add_message(
                message["content"], message["role"], message["id"], prepend=True, scroll=False
            )

        def restore_position() -> None:
            bar.setValue(old_value + bar.maximum() - old_maximum)

        QTimer.singleShot(0, restore_position)

    def accept_user_message(self, message: dict) -> None:
        self.add_message(message["content"], "user", str(message["id"]))
        self.input.clear()
        self.input.setFocus()

    def start_assistant_message(self, message_id: str) -> None:
        if message_id not in self._message_by_id:
            self.add_message("", "assistant", message_id)

    def append_assistant_delta(self, message_id: str, delta: str) -> None:
        bubble = self._message_by_id.get(message_id)
        if bubble is None:
            bubble = self.add_message("", "assistant", message_id)
        bubble.append_text(delta)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def finish_assistant_message(self, message: dict) -> None:
        message_id = str(message["id"])
        bubble = self._message_by_id.get(message_id)
        if bubble is None:
            bubble = self.add_message("", "assistant", message_id)
        bubble.set_text(str(message.get("content") or ""))
        QTimer.singleShot(0, self._scroll_to_bottom)

    def set_chat_available(self, available: bool) -> None:
        self._chat_available = available
        self._update_send_state()

    def set_sending(self, sending: bool) -> None:
        self._sending = sending
        self._update_send_state()

    def set_history_paging(self, has_more: bool, loading: bool) -> None:
        self._history_has_more = has_more
        self._history_loading = loading

    def finish_initial_load(self, has_more: bool) -> None:
        """Position the newest page at the bottom before enabling upward paging."""
        self.set_history_paging(has_more, True)

        def settle_scroll_position() -> None:
            self._scroll_to_bottom()
            self.set_history_paging(has_more, False)

        # QScrollArea recalculates its range after the message layout settles.
        QTimer.singleShot(0, lambda: QTimer.singleShot(0, settle_scroll_position))

    def _on_scroll(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if (
            bar.maximum() > 0
            and value <= 40
            and self._history_has_more
            and not self._history_loading
        ):
            self.load_older_requested.emit()

    def _remove_welcome_state(self) -> None:
        while self.message_layout.count():
            self.message_layout.takeAt(0)
        self.welcome.hide()
        self.message_layout.addStretch(1)

    def clear_messages(self) -> None:
        """Reset message widgets when another in-memory conversation is selected."""
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.welcome:
                widget.deleteLater()
        self.messages.clear()
        self._rows.clear()
        self._message_by_id.clear()
        self.message_layout.addStretch(1)
        self.message_layout.addWidget(self.welcome, 0, Qt.AlignmentFlag.AlignHCenter)
        self.welcome.show()
        self.message_layout.addStretch(2)
        self._history_has_more = False
        self._history_loading = False

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def focus_input(self) -> None:
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
