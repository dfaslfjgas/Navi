# Agent 进程（预留）

本目录预留模型、工具和 Agent 业务运行时，目前尚未接入具体实现。

FastAPI 已由 `app.py` 作为独立子进程启动，仅监听 `127.0.0.1`。GUI 通过
`gui/api/` 中按领域划分的 HTTP/SSE 客户端与服务通信；端口由
`common/config.py` 统一配置。Qt 退出时，`app.py` 会同步停止并回收 FastAPI
子进程。GUI 进程不直接导入 Agent 实现。
