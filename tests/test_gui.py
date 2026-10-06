"""State/regression tests; real desktop interactions are a separate acceptance step."""

import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sys
import threading
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QEventLoop, QPoint, QRect, QSize, QTimer, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QSystemTrayIcon

from common.config import AppConfig
from gui.hotkey import GlobalHotkey, HOTKEY_ID, MOD_NOREPEAT, WM_HOTKEY
from gui.icons import APP_ICON_PATH, ASSET_DIR, app_icon, asset_icon
from gui.api import (
    NaviApi,
    parse_chat_list,
    parse_messages,
    parse_setting_detail,
    parse_settings,
)
from gui.main import GuiController
from gui.tray import NaviTray
from gui.window import NaviPanel, logical_size_for_screen, popup_position_near_cursor


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.panel = NaviPanel(AppConfig())
        self.api = NaviApi("http://127.0.0.1:8765/api/v1", self.panel)
        for owner, methods in (
            (
                self.api.chat_items,
                (
                    "get_chat_items",
                    "create_chat_item",
                    "rename_chat_item",
                    "delete_chat_item",
                ),
            ),
            (self.api.chat_content, ("get_chat_content",)),
            (self.api.agent, ("send_message",)),
            (
                self.api.settings,
                (
                    "get_settings",
                    "get_setting",
                    "create_setting",
                    "update_setting",
                    "delete_setting",
                    "test_setting",
                ),
            ),
        ):
            for method in methods:
                setattr(owner, method, Mock())
        self.panel.attach_api(self.api)

    def tearDown(self):
        self.panel.hide()
        self.panel.deleteLater()
        APP.processEvents()

    def test_hidden_start_chat_content_no_maximize(self):
        self.assertFalse(self.panel.isVisible())
        self.assertIs(self.panel.content, self.panel.chat)
        self.assertTrue(self.panel.chat.welcome.isVisibleTo(self.panel.chat))
        self.assertEqual(self.panel.chat.messages, [])
        self.assertFalse(self.panel.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
        self.assertEqual(self.panel.minimumSize(), self.panel.maximumSize())
        self.panel.show_panel()
        QTest.mouseDClick(self.panel.title_bar, Qt.MouseButton.LeftButton, pos=QPoint(80, 20))
        self.assertFalse(self.panel.isMaximized())

    def test_corgi_svg_is_the_application_icon(self):
        self.assertTrue(APP_ICON_PATH.is_file())
        self.assertEqual(APP_ICON_PATH.name, "corgi.svg")
        self.assertEqual(APP_ICON_PATH.parent, ASSET_DIR)
        self.assertFalse(app_icon().isNull())
        self.assertFalse(app_icon().pixmap(32, 32).isNull())

    def test_new_chat_welcome_uses_corgi_icon(self):
        mark = self.panel.chat.welcome_mark
        self.assertEqual(mark.text(), "")
        self.assertIsNotNone(mark.pixmap())
        self.assertFalse(mark.pixmap().isNull())
        self.assertEqual(mark.accessibleName(), "Navi 小狗图标")

    def test_popup_position_prefers_below_and_right_of_cursor(self):
        position = popup_position_near_cursor(
            QPoint(100, 100), QRect(0, 0, 1920, 1080), QSize(420, 560)
        )
        self.assertEqual(position, QPoint(112, 112))

    def test_popup_position_flips_and_stays_inside_screen_edges(self):
        position = popup_position_near_cursor(
            QPoint(1900, 1060), QRect(0, 0, 1920, 1080), QSize(420, 560)
        )
        self.assertEqual(position, QPoint(1468, 488))
        small_screen_position = popup_position_near_cursor(
            QPoint(-10, -10), QRect(-100, -100, 300, 300), QSize(420, 560)
        )
        self.assertEqual(small_screen_position, QPoint(-100, -100))

    def test_popup_centers_in_middle_and_respects_second_screen_origin(self):
        primary = QRect(0, 0, 1920, 1032)
        secondary = QRect(1920, 0, 1536, 816)
        size = QSize(420, 560)
        self.assertEqual(popup_position_near_cursor(QPoint(800, 500), primary, size), QPoint(812, 220))
        self.assertEqual(popup_position_near_cursor(QPoint(1930, 400), secondary, size), QPoint(1942, 120))
        self.assertEqual(popup_position_near_cursor(QPoint(3440, 790), secondary, size), QPoint(3008, 218))

    def test_window_physical_size_is_stable_across_monitor_dpi(self):
        base = QSize(420, 560)
        self.assertEqual(logical_size_for_screen(base, 1.0), QSize(420, 560))
        self.assertEqual(logical_size_for_screen(base, 1.25), QSize(336, 448))
        self.assertEqual(logical_size_for_screen(base, 1.5), QSize(280, 373))
        self.assertEqual(logical_size_for_screen(base, 2.0), QSize(280, 360))

    def test_window_size_fits_small_and_portrait_screens(self):
        base = QSize(420, 560)
        self.assertEqual(
            logical_size_for_screen(base, 1.0, QSize(800, 480)),
            QSize(420, 448),
        )
        self.assertEqual(
            logical_size_for_screen(base, 1.25, QSize(300, 400)),
            QSize(268, 368),
        )

    def test_sidebar_floats_left_and_loads_http_results(self):
        self.panel.show_panel()
        button = self.panel.title_bar.history_button
        self.assertEqual(button.toolTip(), "展示对话")
        button.click()
        self.assertTrue(self.panel.history.isVisible())
        self.assertEqual(button.toolTip(), "隐藏对话")
        self.assertEqual(self.panel.width(), 420)
        self.assertLess(self.panel.history.x(), self.panel.x())
        self.api.chat_items.get_chat_items.assert_called_once_with()
        records = [
            {"id": "c1", "name": "第一段对话", "activity_time": "2026-10-06T02:00:02.000001Z"},
            {"id": "c2", "name": "第二段对话", "activity_time": "2026-10-06T02:00:01.000001Z"},
        ]
        self.api.chat_items.chats_loaded.emit(records, True, False)
        self.assertEqual(self.panel.history.list.count(), 2)
        first = self.panel.history.list.itemWidget(self.panel.history.list.item(0))
        first.selected.emit("c1")
        self.api.chat_content.get_chat_content.assert_called_once_with("c1")
        messages = [{
            "id": "m1", "role": "user", "content": "第一条消息",
            "status": "completed", "created_time": "2026-10-06T02:00:00.000001Z",
        }]
        self.api.chat_content.messages_loaded.emit("c1", messages, True, False)
        self.assertEqual(self.panel.chat.messages[0].label.text(), "第一条消息")
        self.panel.load_more_content()
        self.api.chat_content.get_chat_content.assert_called_with(
            "c1", "2026-10-06T02:00:00.000001Z"
        )
        second = self.panel.history.list.itemWidget(self.panel.history.list.item(1))
        second.selected.emit("c2")
        self.api.chat_content.get_chat_content.assert_called_with("c2")
        self.assertEqual(self.panel.chat.messages, [])
        self.panel.history.refresh_button.click()
        self.assertEqual(self.api.chat_items.get_chat_items.call_count, 2)
        self.panel.history.new_button.click()
        self.api.chat_items.create_chat_item.assert_called_once()
        button.click()
        self.assertFalse(self.panel.history.isVisible())
        self.assertEqual(button.toolTip(), "展示对话")

    def test_history_context_menu_renames_and_deletes_after_http_success(self):
        self.api.chat_items.chats_loaded.emit(
            [{"id": "c1", "name": "旧名称", "activity_time": "2026-10-06T02:00:00.000001Z"}],
            False, False,
        )
        row = self.panel.history.list.itemWidget(self.panel.history.list.item(0))
        self.assertFalse(row.more.icon().pixmap(18, 18).isNull())
        with patch("gui.window.QInputDialog.getText", return_value=("新名称", True)):
            row.menu.actions()[0].trigger()
        self.api.chat_items.rename_chat_item.assert_called_once_with("c1", "新名称")
        self.api.chat_items.chat_renamed.emit({"id": "c1", "name": "新名称"})
        row = self.panel.history.list.itemWidget(self.panel.history.list.item(0))
        self.assertEqual(row.title.text(), "新名称")
        with patch("gui.window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            row.menu.actions()[1].trigger()
        self.api.chat_items.delete_chat_item.assert_called_once_with("c1")
        self.api.chat_items.chat_deleted.emit("c1")
        self.assertEqual(self.panel.history.list.count(), 0)

    def test_refresh_and_more_icons_load(self):
        self.assertFalse(asset_icon("refresh.svg").pixmap(24, 24).isNull())
        self.assertFalse(asset_icon("more-horizontal.svg").pixmap(24, 24).isNull())
        self.assertFalse(asset_icon("display.svg").pixmap(24, 24).isNull())
        self.assertFalse(asset_icon("hide.svg").pixmap(24, 24).isNull())

    def test_toolbar_uses_downloaded_icons(self):
        self.assertTrue((ASSET_DIR / "pin.svg").is_file())
        self.assertTrue((ASSET_DIR / "settings.svg").is_file())
        self.assertFalse(asset_icon("pin.svg").pixmap(24, 24).isNull())
        self.assertFalse(asset_icon("settings.svg").pixmap(24, 24).isNull())
        self.assertEqual(self.panel.title_bar.settings_button.toolTip(), "设置")

    def test_settings_button_opens_configuration_manager(self):
        self.panel.title_bar.settings_button.click()
        dialog = self.panel.settings_dialog
        self.assertIsNotNone(dialog)
        self.api.settings.get_settings.assert_called_once_with()

        self.api.settings.settings_loaded.emit([
            {"setting_id": "s1", "name": "当前配置", "active": True},
            {"setting_id": "s2", "name": "备用配置", "active": False},
        ])
        first_row = dialog.rows.itemAt(0).widget()
        second_row = dialog.rows.itemAt(1).widget()
        self.assertEqual(first_row.name_label.text(), "当前配置")
        self.assertTrue(first_row.active_check.isChecked())

        first_row.active_check.click()
        self.api.settings.update_setting.assert_called_once_with("s1", active=False)
        self.api.settings.setting_updated.emit({"setting_id": "s1", "active": False})
        self.api.settings.settings_loaded.emit([
            {"setting_id": "s1", "name": "当前配置", "active": False},
            {"setting_id": "s2", "name": "备用配置", "active": False},
        ])
        first_row = dialog.rows.itemAt(0).widget()
        second_row = dialog.rows.itemAt(1).widget()
        self.assertFalse(dialog.test_button.isEnabled())

        second_row.active_check.click()
        self.api.settings.update_setting.assert_called_with("s2", active=True)

        first_row.edit_button.click()
        self.api.settings.get_setting.assert_called_once_with("s1")
        self.api.settings.setting_loaded.emit({
            "setting_id": "s1",
            "name": "当前配置",
            "model_provider": "openai",
            "model_name": "model-a",
            "api_key": "key-a",
            "base_url": "https://example.com/v1",
            "active": True,
            "created_at": "",
            "updated_at": "",
        })
        editor = dialog._editor
        self.assertIsNone(editor.active_check)
        self.assertEqual(
            [editor.provider_combo.itemData(index) for index in range(3)],
            ["openai", "anthropic", "google_genai"],
        )
        self.assertEqual(
            editor.provider_combo.itemText(0),
            "OpenAI（国内模型可选择）",
        )
        self.assertEqual(editor.key_edit.text(), "key-a")
        self.assertEqual(editor.key_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(editor.key_visibility_action.toolTip(), "显示 API Key")
        self.assertFalse(editor.key_visibility_action.icon().isNull())
        editor.key_visibility_action.trigger()
        self.assertEqual(editor.key_edit.echoMode(), QLineEdit.EchoMode.Normal)
        self.assertEqual(editor.key_visibility_action.toolTip(), "隐藏 API Key")
        self.assertFalse(editor.key_visibility_action.icon().isNull())
        self.assertEqual(editor.key_edit.text(), "key-a")
        editor.key_visibility_action.trigger()
        self.assertEqual(editor.key_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(editor.key_visibility_action.toolTip(), "显示 API Key")

    def test_send_button_adds_user_message_and_emits(self):
        submitted = []
        self.panel.message_submitted.connect(submitted.append)
        self.api.chat_items.chat_created.emit({
            "id": "c1", "name": "新对话", "activity_time": "2026-10-06T02:00:00.000001Z"
        })
        self.panel.chat.input.setPlainText("  你好，Navi  ")
        self.assertTrue(self.panel.chat.send_button.isEnabled())
        self.panel.chat.send_button.click()
        self.assertEqual(submitted, ["你好，Navi"])
        self.api.agent.send_message.assert_called_once_with("c1", "你好，Navi")
        self.assertEqual(len(self.panel.chat.messages), 0)
        self.assertFalse(self.panel.chat.send_button.isEnabled())
        self.api.agent.message_accepted.emit("c1", "r1", {
            "id": "m1", "role": "user", "content": "你好，Navi",
            "status": "completed", "created_time": "2026-10-06T02:00:01.000001Z",
        })
        self.assertEqual(len(self.panel.chat.messages), 1)
        self.assertEqual(self.panel.chat.messages[0].role, "user")
        self.assertEqual(self.panel.chat.messages[0].label.text(), "你好，Navi")
        self.assertEqual(self.panel.chat.input.toPlainText(), "")
        self.assertFalse(self.panel.chat.welcome.isVisible())
        self.assertFalse(self.panel.chat.send_button.isEnabled())
        self.api.agent.stream_started.emit("r1", "m2")
        self.api.agent.stream_delta.emit("r1", "m2", "你好")
        self.api.agent.stream_completed.emit("r1", {
            "id": "m2", "role": "assistant", "content": "你好！",
            "status": "completed", "created_time": "2026-10-06T02:00:02.000001Z",
        })
        self.assertEqual(self.panel.chat.messages[-1].label.text(), "你好！")
        self.panel.chat.input.setPlainText("下一条")
        self.assertTrue(self.panel.chat.send_button.isEnabled())

    def test_enter_sends_and_shift_enter_inserts_newline(self):
        submitted = []
        self.panel.chat.message_submitted.connect(submitted.append)
        self.panel._active_chat_id = "c1"
        self.panel.chat.set_chat_available(True)
        self.panel.chat.input.setFocus()
        self.panel.chat.input.setPlainText("第一行")
        self.panel.chat.input.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(
            self.panel.chat.input,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.panel.chat.input.insertPlainText("第二行")
        self.assertEqual(self.panel.chat.input.toPlainText(), "第一行\n第二行")
        QTest.keyClick(self.panel.chat.input, Qt.Key.Key_Return)
        self.assertEqual(submitted, ["第一行\n第二行"])

    def test_assistant_message_is_left_aligned(self):
        bubble = self.panel.chat.add_message("你好，我是 Navi。", "assistant")
        self.assertEqual(bubble.role, "assistant")
        self.assertEqual(bubble.label.text(), "你好，我是 Navi。")

    def test_messages_stay_at_bottom_and_older_messages_prepend(self):
        chat = self.panel.chat
        chat.add_message("较新的消息", "assistant", "m2")
        APP.processEvents()
        first_row = chat._rows[0]
        self.assertEqual(chat.message_layout.indexOf(first_row), 1)

        chat.prepend_messages([{
            "id": "m1", "role": "user", "content": "较早的消息",
            "status": "completed", "created_time": "2026-10-06T01:00:00.000001Z",
        }])
        APP.processEvents()
        self.assertEqual([bubble.label.text() for bubble in chat.messages], ["较早的消息", "较新的消息"])
        self.assertEqual(chat.message_layout.indexOf(chat._rows[0]), 1)

    def test_initial_latest_page_scrolls_to_bottom_before_enabling_older_page(self):
        self.panel.show()
        self.panel._active_chat_id = "c1"
        messages = [
            {
                "id": f"m{index}", "role": "assistant",
                "content": f"第 {index} 条最新消息：" + "内容" * 12,
                "status": "completed",
                "created_time": f"2026-10-06T02:00:{index:02d}.000001Z",
            }
            for index in range(30)
        ]
        self.panel._on_messages_loaded("c1", messages, True, False)
        for _ in range(4):
            APP.processEvents()
        bar = self.panel.chat.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertEqual(bar.value(), bar.maximum())
        self.assertEqual(self.panel.chat.messages[0].message_id, "m0")
        self.assertEqual(self.panel.chat.messages[-1].message_id, "m29")
        self.api.chat_content.get_chat_content.reset_mock()
        bar.setValue(0)
        APP.processEvents()
        self.api.chat_content.get_chat_content.assert_called_once_with(
            "c1", "2026-10-06T02:00:00.000001Z"
        )

    def test_pin_cancel_and_hidden_state_keep_geometry(self):
        self.panel.show_panel()
        self.panel.move(80, 100)
        before = self.panel.geometry()
        self.panel.title_bar.pin_button.click()
        self.assertTrue(self.panel.pinned)
        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(self.panel.geometry(), before)
        self.panel.close()
        self.assertFalse(self.panel.isVisible())
        with patch("gui.window.QCursor.pos", return_value=QPoint(100, 100)):
            self.panel.show_panel()
        self.assertTrue(self.panel.pinned)
        self.assertEqual(
            self.panel.pos(),
            popup_position_near_cursor(QPoint(100, 100), APP.primaryScreen().availableGeometry(), self.panel.size()),
        )
        reopened = self.panel.geometry()
        self.panel.title_bar.pin_button.click()
        self.assertFalse(self.panel.pinned)
        self.assertFalse(self.panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(self.panel.geometry(), reopened)
        self.panel.hide()
        self.panel.set_pinned(True)
        self.assertFalse(self.panel.isVisible())

    def test_native_pin_path_does_not_recreate_or_reposition(self):
        self.panel.show_panel()
        before = self.panel.geometry()
        with patch.object(self.panel, "_set_native_topmost", return_value=True), patch.object(self.panel, "showNormal") as reshow:
            self.panel.title_bar.pin_button.click()
            self.assertTrue(self.panel.pinned)
            self.assertEqual(self.panel.geometry(), before)
            reshow.assert_not_called()
            self.panel.title_bar.pin_button.click()
            self.assertFalse(self.panel.pinned)
            self.assertEqual(self.panel.geometry(), before)
            reshow.assert_not_called()

    def test_close_and_escape_hide_without_quitting(self):
        self.panel.show_panel()
        self.panel.title_bar.close_button.click()
        self.assertFalse(self.panel.isVisible())
        self.panel.show_panel()
        self.panel.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(self.panel.isVisible())
        self.panel.show_panel()
        self.panel.chat.input.setFocus()
        QTest.keyClick(self.panel.chat.input, Qt.Key.Key_Escape)
        self.assertFalse(self.panel.isVisible())
        self.panel.show_panel()
        self.panel.close()
        self.assertFalse(self.panel.isVisible())
        self.assertFalse(APP.quitOnLastWindowClosed())

    def test_title_drag_moves_window(self):
        self.panel.show_panel()
        self.panel.move(40, 50)
        bar = self.panel.title_bar
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(80, 20))
        QTest.mouseMove(bar, QPoint(110, 40))
        QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(110, 40))
        self.assertEqual(self.panel.pos(), QPoint(70, 70))


class TrayTests(unittest.TestCase):
    def test_tray_activation_routes_only_clicks_and_menu(self):
        show = Mock()
        quit_app = Mock()
        tray = NaviTray(show, quit_app)
        tray._activated(QSystemTrayIcon.ActivationReason.Context)
        show.assert_not_called()
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
        tray.show_action.trigger()
        self.assertEqual(show.call_count, 3)
        tray.quit_action.trigger()
        quit_app.assert_called_once_with()


class NaviApiTests(unittest.TestCase):
    def test_parse_documented_responses(self):
        records, has_more = parse_chat_list({
            "result": True,
            "data": {"items": [{
                "id": "c1", "name": "计划",
                "activity_time": "2026-10-06T02:00:00.000001Z",
            }], "has_more": True},
            "error": None,
        })
        self.assertEqual(records[0]["id"], "c1")
        self.assertEqual(records[0]["name"], "计划")
        self.assertTrue(has_more)
        messages, has_more = parse_messages({
            "result": True,
            "data": {"items": [{
                "id": "m1", "role": "user", "content": "你好",
                "status": "completed", "created_time": "2026-10-06T02:00:01.000001Z",
            }], "has_more": False},
            "error": None,
        })
        self.assertEqual(messages[0]["id"], "m1")
        self.assertEqual(messages[0]["content"], "你好")
        self.assertFalse(has_more)
        settings = parse_settings({
            "result": True,
            "data": [{
                "setting_id": "setting_1",
                "name": "本地模型",
                "active": True,
            }],
            "error": None,
        })
        self.assertEqual(settings[0]["setting_id"], "setting_1")
        self.assertEqual(settings[0], {
            "setting_id": "setting_1",
            "name": "本地模型",
            "active": True,
        })
        detail = parse_setting_detail({
            "result": True,
            "data": {
                "setting_id": "setting_1",
                "name": "本地模型",
                "model_provider": "openai",
                "model_name": "model-a",
                "api_key": "key-a",
                "base_url": "http://127.0.0.1:11434/v1",
                "active": True,
            },
            "error": None,
        })
        self.assertEqual(detail["model_name"], "model-a")
        self.assertEqual(detail["model_provider"], "openai")
        self.assertTrue(detail["active"])

    def test_request_paths_and_methods(self):
        api = NaviApi("http://127.0.0.1:8765/api/v1")
        with patch.object(api.transport, "request") as request:
            api.chat_items.get_chat_items()
            self.assertEqual(request.call_args.args[:3], ("chats", "GET", "/chats?page_size=30"))
            api.chat_items.get_chat_items("2026-10-06T02:00:00.000001Z", 25)
            self.assertEqual(
                request.call_args.args[:3],
                ("chats", "GET", "/chats?page_size=25&activity_time_lt=2026-10-06T02%3A00%3A00.000001Z"),
            )
            api.chat_content.get_chat_content(
                "chat/a",
                "2026-10-06T01:00:00.000001Z",
                20,
            )
            self.assertEqual(request.call_args.args[:3], (
                "messages", "GET",
                "/chat_content/chat%2Fa/messages?page_size=20&created_time_lt=2026-10-06T01%3A00%3A00.000001Z",
            ))
            api.chat_items.create_chat_item()
            self.assertEqual(request.call_args.args[:3], ("create_chat", "POST", "/chats"))
            api.chat_items.rename_chat_item("chat/a", "新标题")
            self.assertEqual(request.call_args.args[:4],
                             ("rename_chat", "PATCH", "/chats/chat%2Fa", {"name": "新标题"}))
            api.chat_items.delete_chat_item("chat/a")
            self.assertEqual(request.call_args.args[:3],
                             ("delete_chat", "DELETE", "/chats/chat%2Fa"))
            api.chat_content.add_chat_content("chat/a", "user", "你好")
            self.assertEqual(
                request.call_args.args[:4],
                (
                    "add_chat_content",
                    "POST",
                    "/chat_content/chat%2Fa/messages",
                    {"role": "user", "content": "你好"},
                ),
            )
            api.agent.send_message("chat/a", "请回复", "client-1")
            self.assertEqual(
                request.call_args.args[:4],
                (
                    "send_message",
                    "POST",
                    "/chats/chat%2Fa/messages",
                    {
                        "content": "请回复",
                        "client_message_id": "client-1",
                    },
                ),
            )
            api.settings.get_settings()
            self.assertEqual(
                request.call_args.args[:3],
                ("get_settings", "GET", "/setting/get_setting"),
            )
            api.settings.get_setting("setting/a")
            self.assertEqual(
                request.call_args.args[:3],
                (
                    "get_setting",
                    "GET",
                    "/setting/get_setting/setting_id/setting%2Fa",
                ),
            )
            api.settings.test_setting()
            self.assertEqual(
                request.call_args.args[:3],
                (
                    "test_setting",
                    "POST",
                    "/setting/test_setting",
                ),
            )
            self.assertEqual(request.call_args.kwargs["timeout_ms"], 25000)
            api.settings.create_setting(
                "OpenAI",
                "openai",
                "model-a",
                "key-a",
                "https://example.com/v1",
                True,
            )
            self.assertEqual(
                request.call_args.args[:4],
                (
                    "create_setting",
                    "POST",
                    "/setting/create_setting",
                    {
                        "name": "OpenAI",
                        "model_provider": "openai",
                        "model_name": "model-a",
                        "api_key": "key-a",
                        "base_url": "https://example.com/v1",
                        "active": True,
                    },
                ),
            )
            api.settings.update_setting("setting/a", active=True)
            self.assertEqual(
                request.call_args.args[:4],
                (
                    "update_setting",
                    "PATCH",
                    "/setting/update_setting/setting_id/setting%2Fa",
                    {"active": True},
                ),
            )
            api.settings.delete_setting("setting/a")
            self.assertEqual(
                request.call_args.args[:3],
                (
                    "delete_setting",
                    "DELETE",
                    "/setting/delete_setting/setting_id/setting%2Fa",
                ),
            )

    def test_async_http_list_round_trip(self):
        paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                body = b'{"result":true,"data":{"items":[{"id":"c1","name":"HTTP chat","activity_time":"2026-10-06T02:00:00.000001Z"}],"has_more":false},"error":null}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = NaviApi(f"http://127.0.0.1:{server.server_port}/api/v1", APP)
            APP._http_test_client = api
            result = []
            loop = QEventLoop()
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            api.chat_items.chats_loaded.connect(
                lambda items, _more, _append: (result.extend(items), loop.quit())
            )
            api.transport.request_failed.connect(
                lambda op, detail: (result.append((op, detail)), loop.quit())
            )
            api.chat_items.get_chat_items()
            timeout.start(3000)
            loop.exec()
            timeout.stop()
            self.assertEqual(paths, ["/api/v1/chats?page_size=30"])
            self.assertEqual(result[0]["id"], "c1")
            self.assertEqual(result[0]["name"], "HTTP chat")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@unittest.skipUnless(sys.platform == "win32", "Windows native API")
class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.show = Mock()
        self.api = Mock()
        self.api.RegisterHotKey.return_value = 1
        self.key = GlobalHotkey(self.app, self.show)
        self.patch = patch("gui.hotkey.ctypes.WinDLL", return_value=self.api)
        self.patch.start()

    def tearDown(self):
        self.key.stop()
        self.patch.stop()

    def test_registration_message_filter_and_release(self):
        self.key.start()
        self.key.start()
        self.api.RegisterHotKey.assert_called_once()
        self.assertIsNone(self.api.RegisterHotKey.call_args.args[0])
        self.assertTrue(self.api.RegisterHotKey.call_args.args[2] & MOD_NOREPEAT)
        native = wintypes.MSG()
        native.message = WM_HOTKEY
        native.wParam = HOTKEY_ID + 1
        event_type = QByteArray(b"windows_dispatcher_MSG")
        self.assertEqual(self.key.nativeEventFilter(event_type, ctypes.addressof(native)), (False, 0))
        self.show.assert_not_called()
        native.wParam = HOTKEY_ID
        self.assertEqual(self.key.nativeEventFilter(event_type, ctypes.addressof(native)), (True, 0))
        self.show.assert_called_once_with()
        self.key.stop()
        self.key.stop()
        self.api.UnregisterHotKey.assert_called_once_with(None, HOTKEY_ID)
        self.app.removeNativeEventFilter.assert_called_once_with(self.key)

    def test_registration_conflict_installs_no_filter(self):
        self.api.RegisterHotKey.return_value = 0
        with self.assertRaises(OSError):
            self.key.start()
        self.app.installNativeEventFilter.assert_not_called()
        self.key.stop()
        self.api.UnregisterHotKey.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def test_start_remains_hidden_and_cleanup_is_idempotent(self):
        controller = GuiController(APP, AppConfig())
        with patch.object(controller.tray, "show"), patch.object(controller.hotkey, "start"), patch.object(controller.hotkey, "stop") as release, patch.object(controller.tray, "stop") as hide:
            controller.start()
            self.assertFalse(controller.panel.isVisible())
            controller.panel.show_panel()
            controller.stop()
            controller.stop()
            release.assert_called_once_with()
            hide.assert_called_once_with()
            self.assertFalse(controller.panel.isVisible())
            self.assertEqual(controller.api.base_url, "http://127.0.0.1:8765/api/v1")
        controller.panel.deleteLater()
        APP.processEvents()

    def test_hotkey_failure_preserves_tray_path(self):
        controller = GuiController(APP, AppConfig())
        with patch.object(controller.tray, "show") as show, patch.object(controller.hotkey, "start", side_effect=OSError("occupied")), patch.object(controller.tray, "report_hotkey_error") as report:
            controller.start()
            show.assert_called_once_with()
            report.assert_called_once()
            controller.tray.show_action.trigger()
            self.assertTrue(controller.panel.isVisible())
        controller.stop()
        controller.panel.deleteLater()
        APP.processEvents()


if __name__ == "__main__":
    unittest.main()
