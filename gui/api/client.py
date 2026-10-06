"""按后端领域组装 GUI API 客户端。"""

from PySide6.QtCore import QObject

from gui.api.agent import AgentApi
from gui.api.chat_content import ChatContentApi
from gui.api.chat_item import ChatItemApi
from gui.api.setting import SettingApi
from gui.api.transport import ApiTransport


class NaviApi(QObject):
    """GUI API 入口；具体调用分别由三个领域客户端负责。"""

    def __init__(self, base_url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.transport = ApiTransport(base_url, self)
        self.chat_items = ChatItemApi(self.transport, self)
        self.chat_content = ChatContentApi(self.transport, self)
        self.agent = AgentApi(self.transport, self)
        self.settings = SettingApi(self.transport, self)

    @property
    def base_url(self) -> str:
        """返回共享的后端 API 根地址。"""
        return self.transport.base_url
