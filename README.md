# Navi：桌面聊天 GUI

面向 Windows 的最小桌面应用，Python 3.10+。运行环境由开发者预先配置。
GUI 使用 PySide6 Essentials，临时服务使用 FastAPI 与 Uvicorn；具体版本记录在
`requirements.txt`。

## 启动

激活已经创建的 Conda 环境。在第一个终端启动临时 HTTP 服务：

```powershell
conda activate Navi
cd D:\Navi
python mock_server.py
```

在第二个终端启动 GUI：

```powershell
conda activate Navi
cd D:\Navi
python app.py
```

也可以在 PyCharm 中选择名为 `Navi` 的解释器，直接运行根目录的 `app.py`。
`requirements.txt` 仅记录项目依赖，不创建或管理虚拟环境。
临时服务预置两条示例对话，数据只在服务进程内存中，关闭服务后新建、重命名和删除的结果会重置。

## 操作

- 启动后面板默认隐藏，Navi 常驻系统托盘。Windows 可能将图标放在托盘的折叠菜单中。
- 系统托盘、窗口和标题栏统一使用 `assets/corgi.svg` 图标。
- 左键单击或双击托盘图标，显示并激活面板；重复触发保持显示。
- 在任意应用中按 `Ctrl+Shift+K` 显示面板，长按不会连续重复触发。
- 面板每次显示时会根据鼠标所在屏幕的可用区域定位：靠左显示在右边，靠右显示在左边，靠上显示在下方，靠下显示在上方，中间则与鼠标垂直居中。
- 点击标题栏左侧的小狗图标，对话侧栏会向主面板左侧独立展开，不压缩聊天区域。侧栏有刷新、新建按钮；每条对话右侧的三点菜单可重命名或删除。
- 右上角的设置图标暂不打开页面；旁边的钉子图标使用 Windows 原生置顶切换，避免窗口闪烁。两个 SVG 都放在 `assets/`。
- 面板包含滚动消息区和多行输入框；`Enter` 发送，`Shift+Enter` 换行。
- 对话列表、历史内容和消息发送都通过本机 HTTP 服务完成。临时 FastAPI 服务支持列表、新建、重命名、删除、时间分页以及 SSE 流式回复；连接失败时侧栏显示错误，可点击刷新重试。
- 发送消息后按钮保持不可点击，收到 SSE `completed` 或 `error` 后恢复；V1 不提供取消按钮。
- 面板通常保持约 420 × 560 物理像素；跨越任意 DPI 的屏幕时自动换算 Qt 逻辑尺寸并重建阴影，避免窗口变大或透明内容失效。在高缩放、小分辨率和竖屏上会保留最小可读尺寸，并自动限制在当前屏幕的可用区域内。窗口无最大化按钮，标题栏双击不最大化。
- 拖动标题栏移动窗口；隐藏和重新显示保留 Pin 状态，重新打开时根据鼠标位置重新定位。
- 关闭按钮、`Alt+F4` 或 `Esc` 只隐藏面板；右键托盘 →「退出 Navi」彻底退出。
- 快捷键被占用时显示托盘提示，点击托盘仍可打开面板。退出占用程序并重启 Navi 可重试。
- 不会自动设置开机启动。当前全局快捷键实现针对 Windows。

## 进程边界

```text
app.py               本阶段仅启动 GUI；未来管理 Agent 子进程生命周期
mock_server.py       FastAPI 临时 HTTP/SSE 服务，示例数据只保存在内存
gui/main.py          QApplication 与 GUI 对象生命周期
gui/window.py        主面板、自定义标题栏、拖动、Pin、隐藏
gui/chat.py          消息列表、消息气泡、输入框与发送信号
gui/history.py       独立弹出的对话侧栏、刷新与每条对话的操作菜单
gui/tray.py          托盘图标与退出菜单
gui/hotkey.py        Windows RegisterHotKey + Qt 原生消息过滤
gui/icons.py         加载项目 SVG，绘制发送和关闭等内置小图标
assets/              全部英文命名的应用、Pin、设置、刷新和更多操作 SVG
gui/api.py           Qt 异步 HTTP、响应解析和 SSE 流处理
common/config.py     GUI 设置及预留 Agent 地址 127.0.0.1:8765
agent/               独立 Agent 进程预留目录，当前没有服务实现
tests/               GUI 状态、托盘路由、原生快捷键消息及退出清理检查
```

GUI 不导入 LangChain、FastAPI 或 Agent 运行时。GUI 本身不监听端口；
临时 FastAPI 服务是独立进程，只监听 `127.0.0.1:8765`，GUI 通过 Qt 异步 HTTP 请求访问它。

## HTTP 接口

新的 V1 接口设计稿见 [`docs/http-api-v1.md`](docs/http-api-v1.md)。设计稿统一了
对话与消息资源、时间分页、错误响应、消息幂等提交、SSE 流式回复、断线重连和
发送状态管理。GUI 客户端与临时 FastAPI 服务已按该文档实现。

## 验证

不显示桌面窗口的自动检查：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s tests -v
Remove-Item Env:QT_QPA_PLATFORM
```

真实 Windows 窗口检查（会短暂显示窗口和托盘，然后自动退出）：

```powershell
python tests/check_windows.py
```

如果全局快捷键已被正在运行的 Navi 或其他程序占用，可单独检查 Pin（不会注册快捷键）：

```powershell
python tests/check_pin_windows.py
```

该检查验证真实 Win32 置顶标志、Qt 原生消息分发、快捷键注册/释放、托盘状态、
固定尺寸和渲染截图，截图保存为项目目录的 `navi-preview.png`。
快捷键消息由测试发送，鼠标点击托盘和实际按键仍需以下桌面验收。

桌面验收：启动后检查托盘；切换到其他应用按快捷键；切换 Pin 后点击其他窗口
确认置顶与取消；隐藏再打开；最后从托盘退出。自动检查不能代替真实桌面的
前台焦点、跨应用层叠和实际鼠标/键盘输入验收。

实现参考：[Qt 托盘文档](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)、
[Qt 原生消息过滤](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractNativeEventFilter.html)、
[Windows RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)。
