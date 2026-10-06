"""模型配置列表及新增、编辑窗口。"""

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.api import NaviApi
from gui.icons import asset_icon


PROVIDER_OPTIONS = (
    ("OpenAI（国内模型可选择）", "openai"),
    ("Anthropic Claude", "anthropic"),
    ("Google Gemini", "google_genai"),
)


class SettingFormDialog(QDialog):
    """收集新增或编辑配置所需字段；编辑模式不提供 active 字段。"""

    def __init__(self, parent=None, *, setting: dict | None = None):
        super().__init__(parent)
        self.setting = setting
        self.setWindowTitle("修改模型配置" if setting else "新增模型配置")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.name_edit = QLineEdit()
        self.provider_combo = QComboBox()
        for label, value in PROVIDER_OPTIONS:
            self.provider_combo.addItem(label, value)
        self.model_edit = QLineEdit()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_visibility_action = self.key_edit.addAction(
            asset_icon("display.svg"),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.key_visibility_action.setText("显示 API Key")
        self.key_visibility_action.setToolTip("显示 API Key")
        self.key_visibility_action.setCheckable(True)
        self.key_visibility_action.toggled.connect(self._set_api_key_visible)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/v1")

        form.addRow("配置名称", self.name_edit)
        form.addRow("模型厂商", self.provider_combo)
        form.addRow("模型名称", self.model_edit)
        form.addRow("API Key", self.key_edit)
        form.addRow("Base URL", self.url_edit)

        self.active_check: QCheckBox | None = None
        if setting is None:
            self.active_check = QCheckBox("创建后立即激活")
            form.addRow("", self.active_check)
        else:
            self.name_edit.setText(setting["name"])
            index = self.provider_combo.findData(setting["model_provider"])
            self.provider_combo.setCurrentIndex(max(index, 0))
            self.model_edit.setText(setting["model_name"])
            self.key_edit.setText(setting["api_key"])
            self.url_edit.setText(setting["base_url"])

        root.addLayout(form)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("保存")
        self.save_button.setDefault(True)
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        self.setStyleSheet("""
            QDialog { background: #f8f9fc; }
            QLineEdit, QComboBox { min-height: 32px; padding: 0 8px;
                border: 1px solid #d8deea; border-radius: 6px; background: white; }
            QPushButton { min-height: 32px; padding: 0 16px; border-radius: 6px;
                border: 1px solid #d8deea; background: white; }
            QPushButton:hover { background: #edf0f7; }
            QPushButton:default { color: white; background: #5268e8; border: none; }
        """)

    def _set_api_key_visible(self, visible: bool) -> None:
        """在明文和密码显示模式之间切换，不改变输入内容。"""
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )
        action = "隐藏" if visible else "显示"
        icon_name = "hide.svg" if visible else "display.svg"
        self.key_visibility_action.setIcon(asset_icon(icon_name))
        self.key_visibility_action.setText(f"{action} API Key")
        self.key_visibility_action.setToolTip(f"{action} API Key")
        self.key_edit.setFocus()
        self.key_edit.setCursorPosition(len(self.key_edit.text()))

    def values(self) -> dict:
        """返回去除首尾空格后的表单数据。"""
        return {
            "name": self.name_edit.text().strip(),
            "model_provider": str(self.provider_combo.currentData()),
            "model_name": self.model_edit.text().strip(),
            "api_key": self.key_edit.text().strip(),
            "base_url": self.url_edit.text().strip(),
        }

    def validate(self) -> bool:
        """在请求前拦截空字段并聚焦第一个错误输入框。"""
        fields = (
            (self.name_edit, "配置名称"),
            (self.model_edit, "模型名称"),
            (self.key_edit, "API Key"),
            (self.url_edit, "Base URL"),
        )
        for widget, label in fields:
            if not widget.text().strip():
                QMessageBox.warning(self, "信息不完整", f"{label}不能为空。")
                widget.setFocus()
                return False
        url = QUrl(self.url_edit.text().strip())
        if url.scheme().lower() not in {"http", "https"} or not url.host():
            QMessageBox.warning(
                self,
                "Base URL 格式错误",
                "Base URL 必须是完整地址，并以 http:// 或 https:// 开头。",
            )
            self.url_edit.setFocus()
            return False
        return True

    def set_saving(self, saving: bool) -> None:
        """请求处理中禁止重复保存。"""
        self.save_button.setEnabled(not saving)
        self.save_button.setText("保存中…" if saving else "保存")


class SettingRow(QFrame):
    """只展示配置名称，并提供编辑、删除和激活控件。"""

    def __init__(self, item: dict, owner: "SettingsDialog"):
        super().__init__()
        self.item = item
        self.setObjectName("settingRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        self.name_label = QLabel(item["name"])
        layout.addWidget(self.name_label, 1)

        self.edit_button = QToolButton()
        self.edit_button.setText("修改")
        self.edit_button.setToolTip("修改配置")
        self.edit_button.clicked.connect(
            lambda: owner.edit_setting(item["setting_id"])
        )
        layout.addWidget(self.edit_button)

        self.delete_button = QToolButton()
        self.delete_button.setText("删除")
        self.delete_button.setToolTip("删除配置")
        self.delete_button.clicked.connect(
            lambda: owner.delete_setting(item["setting_id"], item["name"])
        )
        layout.addWidget(self.delete_button)

        self.active_check = QCheckBox()
        self.active_check.setToolTip("当前使用的模型配置")
        self.active_check.setAccessibleName(f"激活配置 {item['name']}")
        self.active_check.setChecked(bool(item.get("active")))
        self.active_check.clicked.connect(
            lambda checked: owner.activate_setting(
                item["setting_id"], checked, self.active_check
            )
        )
        layout.addWidget(self.active_check)


class SettingsDialog(QDialog):
    """通过 HTTP 管理后端模型配置。"""

    def __init__(self, api: NaviApi, parent=None):
        super().__init__(parent)
        self.api = api
        self._items: list[dict] = []
        self._editor: SettingFormDialog | None = None
        self._editing_setting_id: str | None = None
        self.setWindowTitle("模型配置")
        self.resize(520, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        heading = QLabel("模型配置")
        heading.setObjectName("settingsHeading")
        root.addWidget(heading)
        hint = QLabel("勾选一项作为 Navi 当前使用的模型配置。")
        hint.setObjectName("settingsHint")
        root.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.rows = QVBoxLayout(self.container)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(8)
        self.rows.addStretch()
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.status = QLabel()
        self.status.setObjectName("settingsStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        actions = QHBoxLayout()
        self.test_button = QPushButton("测试当前配置")
        self.test_button.clicked.connect(self.test_active_setting)
        self.add_button = QPushButton("新增配置")
        self.add_button.clicked.connect(self.add_setting)
        actions.addWidget(self.test_button)
        actions.addStretch()
        actions.addWidget(self.add_button)
        root.addLayout(actions)

        api.settings.settings_loaded.connect(self._show_items)
        api.settings.setting_loaded.connect(self._show_editor)
        api.settings.setting_created.connect(self._saved)
        api.settings.setting_updated.connect(self._saved)
        api.settings.setting_deleted.connect(self._deleted)
        api.settings.setting_tested.connect(self._tested)
        api.transport.request_failed.connect(self._request_failed)

        self.setStyleSheet("""
            QDialog { background: #f8f9fc; }
            QLabel#settingsHeading { color: #232b3d; font-size: 18px; font-weight: 650; }
            QLabel#settingsHint, QLabel#settingsStatus { color: #7c8598; }
            QFrame#settingRow { background: white; border: 1px solid #dde2eb;
                border-radius: 8px; }
            QToolButton { min-height: 28px; padding: 0 8px; border: none;
                border-radius: 5px; color: #5268e8; }
            QToolButton:hover { background: #edf0f7; }
            QPushButton { min-height: 34px; padding: 0 16px; border-radius: 7px;
                border: 1px solid #d8deea; background: white; }
            QPushButton:hover { background: #edf0f7; }
        """)

    def refresh(self) -> None:
        self.status.setText("正在读取配置…")
        self.api.settings.get_settings()

    def _clear_rows(self) -> None:
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_items(self, items: list[dict]) -> None:
        self._items = items
        self._clear_rows()
        if not items:
            empty = QLabel("还没有模型配置，请点击“新增配置”。")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rows.insertWidget(0, empty)
        else:
            for item in items:
                self.rows.insertWidget(self.rows.count() - 1, SettingRow(item, self))
        self.status.setText("")
        self.test_button.setEnabled(any(item.get("active") for item in items))

    def add_setting(self) -> None:
        self._editing_setting_id = None
        self._editor = SettingFormDialog(self)
        self._editor.save_button.clicked.connect(self._create_from_form)
        self._editor.open()

    def edit_setting(self, setting_id: str) -> None:
        self._editing_setting_id = setting_id
        self.status.setText("正在读取配置详情…")
        self.api.settings.get_setting(setting_id)

    def _show_editor(self, setting: dict) -> None:
        if setting["setting_id"] != self._editing_setting_id:
            return
        self.status.setText("")
        self._editor = SettingFormDialog(self, setting=setting)
        self._editor.save_button.clicked.connect(self._update_from_form)
        self._editor.open()

    def _create_from_form(self) -> None:
        if self._editor is None or not self._editor.validate():
            return
        values = self._editor.values()
        active = bool(self._editor.active_check and self._editor.active_check.isChecked())
        self._editor.set_saving(True)
        self.api.settings.create_setting(**values, active=active)

    def _update_from_form(self) -> None:
        if (
            self._editor is None
            or self._editing_setting_id is None
            or not self._editor.validate()
        ):
            return
        self._editor.set_saving(True)
        self.api.settings.update_setting(
            self._editing_setting_id,
            **self._editor.values(),
        )

    def delete_setting(self, setting_id: str, name: str) -> None:
        answer = QMessageBox.question(
            self,
            "删除模型配置",
            f"确定删除“{name}”吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.status.setText("正在删除配置…")
            self.api.settings.delete_setting(setting_id)

    def activate_setting(
        self, setting_id: str, checked: bool, checkbox: QCheckBox
    ) -> None:
        for row_index in range(self.rows.count() - 1):
            row = self.rows.itemAt(row_index).widget()
            if isinstance(row, SettingRow):
                row.active_check.setEnabled(False)
        self.test_button.setEnabled(False)
        self.status.setText(
            "正在激活配置…" if checked else "正在取消激活配置…"
        )
        self.api.settings.update_setting(setting_id, active=checked)

    def test_active_setting(self) -> None:
        self.test_button.setEnabled(False)
        self.status.setText("正在测试当前配置…")
        self.api.settings.test_setting()

    def _saved(self, _setting: dict) -> None:
        if self._editor is not None:
            self._editor.accept()
            self._editor = None
        self._editing_setting_id = None
        self.status.setText("配置已保存。")
        self.api.settings.get_settings()

    def _deleted(self, _setting_id: str) -> None:
        self.status.setText("配置已删除。")
        self.api.settings.get_settings()

    def _tested(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        reply = str(result.get("reply") or "连接成功")
        self.status.setText(f"测试成功：{reply}")

    def _request_failed(self, operation: str, detail: str) -> None:
        if operation not in {
            "get_settings", "get_setting", "create_setting", "update_setting",
            "delete_setting", "test_setting",
        }:
            return
        if self._editor is not None:
            self._editor.set_saving(False)
            if operation in {"create_setting", "update_setting"}:
                QMessageBox.warning(self._editor, "保存失败", detail)
        if operation == "update_setting":
            active_by_id = {
                item["setting_id"]: bool(item.get("active"))
                for item in self._items
            }
            for row_index in range(self.rows.count() - 1):
                row = self.rows.itemAt(row_index).widget()
                if isinstance(row, SettingRow):
                    row.active_check.blockSignals(True)
                    row.active_check.setChecked(
                        active_by_id.get(row.item["setting_id"], False)
                    )
                    row.active_check.setEnabled(True)
                    row.active_check.blockSignals(False)
        self.test_button.setEnabled(any(item.get("active") for item in self._items))
        self.status.setText(f"操作失败：{detail}")
