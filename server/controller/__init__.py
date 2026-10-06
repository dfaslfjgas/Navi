"""聚合全部 Controller，供 FastAPI 应用一次性挂载。"""

from fastapi import APIRouter

from server.controller.agent import router as agent_router
from server.controller.chat_content import router as chat_content_router
from server.controller.chat_item import router as chat_item_router
from server.controller.setting import router as setting_router


# 所有业务接口共用版本前缀；server.main 只需 include_router 一次。
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_item_router)
api_router.include_router(chat_content_router)
api_router.include_router(agent_router)
api_router.include_router(setting_router)


__all__ = ["api_router"]
