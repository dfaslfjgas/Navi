# Agent 进程（预留）

本阶段没有可执行 Agent，也不启动 HTTP 服务。

后续 Agent 将作为独立进程运行，仅监听 `127.0.0.1`。GUI 通过
`gui/api.py` 中的 HTTP/SSE 客户端与它通信；模型、工具和业务运行时全部放在
此目录。端口由 `common/config.py` 统一配置。未来在 `app.py` 添加子进程
启动、就绪检查与退出清理，GUI 进程不直接导入 Agent 实现。
