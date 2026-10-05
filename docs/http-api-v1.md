# Navi HTTP API V1

状态：待 Review  
更新时间：2026-10-06

服务地址：

```text
http://127.0.0.1:8765/api/v1
```

公共约定：

- 普通请求和响应使用 JSON，字段名使用 `snake_case`。
- ID 使用字符串，客户端不比较 ID 的大小。
- 时间使用 UTC RFC 3339 格式并保留微秒，例如 `2026-10-06T02:30:00.123456Z`。
- 对话列表使用 `activity_time_lt` 加载更早的数据，历史消息使用 `created_time_lt` 加载更早的数据。
- 服务端保证同一分页序列中的时间值单调且不重复；如果新时间没有大于上一条时间，则在上一条时间上增加 1 微秒。
- `page_size` 默认是 `30`，范围是 `1～100`。
- 普通接口成功时返回 `result: true`，失败时返回 `result: false` 和 `error`。

## 1、获取对话列表

URL

```http
GET /api/v1/chats
```

参数

Query 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `activity_time_lt` | 否 | string | 只返回活动时间早于该值的对话；首次请求不传 |
| `page_size` | 否 | integer | 每页数量，默认 `30` |

对话按照 `activity_time DESC` 排序。创建对话或新增消息时更新 `activity_time`，重命名不会改变 `activity_time`。

继续加载时，GUI 取当前列表最后一项的 `activity_time` 作为下一次请求的 `activity_time_lt`。点击刷新时不传该参数，重新获取最新数据。

返回值

```json
{
  "result": true,
  "data": {
    "items": [
      {
        "id": "chat_102",
        "name": "接口设计讨论",
        "created_at": "2026-10-06T02:20:00Z",
        "updated_at": "2026-10-06T02:35:00Z",
        "activity_time": "2026-10-06T02:34:00.123456Z"
      }
    ],
    "has_more": true
  },
  "error": null
}
```

没有更多数据时：

```json
{
  "result": true,
  "data": {
    "items": [],
    "has_more": false
  },
  "error": null
}
```

## 2、删除指定对话

URL

```http
DELETE /api/v1/chats/{chat_id}
```

参数

Path 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | 是 | string | 要删除的对话 ID |

删除对话时同时删除历史消息。如果该对话仍有运行中的 Agent 任务，则返回 HTTP `409 CHAT_BUSY`，任务结束后才能删除。

返回值

```json
{
  "result": true,
  "data": {
    "id": "chat_102"
  },
  "error": null
}
```

对话不存在时返回 HTTP `404`：

```json
{
  "result": false,
  "data": null,
  "error": {
    "code": "CHAT_NOT_FOUND",
    "message": "对话不存在"
  }
}
```

## 3、重命名指定对话

URL

```http
PATCH /api/v1/chats/{chat_id}
Content-Type: application/json
```

参数

Path 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | 是 | string | 要重命名的对话 ID |

Body 参数：

```json
{
  "name": "新的对话名称"
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `name` | 是 | string | 去除首尾空格后不能为空，最长 100 个字符 |

返回值

```json
{
  "result": true,
  "data": {
    "id": "chat_102",
    "name": "新的对话名称",
    "created_at": "2026-10-06T02:20:00Z",
    "updated_at": "2026-10-06T02:40:00Z",
    "activity_time": "2026-10-06T02:34:00.123456Z"
  },
  "error": null
}
```

## 4、新建对话

URL

```http
POST /api/v1/chats
Content-Type: application/json
```

参数

Body 参数：

```json
{
  "name": "新对话"
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `name` | 否 | string | 省略或传 `null` 时使用“新对话”；最长 100 个字符 |

返回值

HTTP 状态码：`201 Created`

```json
{
  "result": true,
  "data": {
    "id": "chat_103",
    "name": "新对话",
    "created_at": "2026-10-06T02:42:00Z",
    "updated_at": "2026-10-06T02:42:00Z",
    "activity_time": "2026-10-06T02:42:00.123456Z"
  },
  "error": null
}
```

## 5、获取对话内容

URL

```http
GET /api/v1/chats/{chat_id}/messages
```

参数

Path 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | 是 | string | 对话 ID |

Query 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `created_time_lt` | 否 | string | 只返回创建时间早于该值的消息；首次请求不传 |
| `page_size` | 否 | integer | 每页数量，默认 `30` |

首次请求返回最近的消息。继续加载时，GUI 取当前消息列表第一项的 `created_time` 作为下一次请求的 `created_time_lt`。每一页的 `items` 始终按照 `created_time ASC` 排列，并插入现有消息列表顶部。

返回值

```json
{
  "result": true,
  "data": {
    "items": [
      {
        "id": "msg_501",
        "role": "user",
        "content": "帮我分析这个接口",
        "status": "completed",
        "created_time": "2026-10-06T02:30:00.123456Z"
      },
      {
        "id": "msg_502",
        "role": "assistant",
        "content": "可以，主要有以下问题……",
        "status": "completed",
        "created_time": "2026-10-06T02:30:02.123456Z"
      }
    ],
    "has_more": true
  },
  "error": null
}
```

`role` 可选值：

```text
user
assistant
system
```

`status` 可选值：

```text
generating
completed
failed
```

## 6.1、提交消息

URL

```http
POST /api/v1/chats/{chat_id}/messages
Content-Type: application/json
```

参数

Path 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | 是 | string | 对话 ID |

Body 参数：

```json
{
  "content": "帮我解释这段代码",
  "client_message_id": "8c84834e-74db-48fd-aac6-b75440ca5db4"
}
```

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `content` | 是 | string | 用户消息，去除首尾空格后不能为空 |
| `client_message_id` | 是 | string | GUI 生成的 UUID，用于防止超时重试产生重复消息 |

同一个对话同时只允许一个未结束的 run。重复发送时返回 HTTP `409 CHAT_BUSY`。

同一个 `chat_id + client_message_id` 重试且内容相同时，返回第一次创建的消息和 run；内容不同时返回 HTTP `409 IDEMPOTENCY_CONFLICT`。

GUI 状态约定：

- 没有正在运行的任务且输入框内容不为空时，发送按钮可以点击。
- 用户点击发送后，发送按钮立即变为不可点击状态，防止重复提交。
- 收到 SSE `completed` 或 `error` 事件后，发送按钮恢复为可点击状态。
- 如果提交消息的 HTTP 请求直接失败，发送按钮也应恢复为可点击状态。
- V1 不提供停止或取消按钮。

返回值

HTTP 状态码：`202 Accepted`

```json
{
  "result": true,
  "data": {
    "run_id": "run_901",
    "user_message": {
      "id": "msg_503",
      "role": "user",
      "content": "帮我解释这段代码",
      "status": "completed",
      "created_time": "2026-10-06T02:50:00.123456Z"
    }
  },
  "error": null
}
```

## 6.2、接收 Agent 流式回复

URL

```http
GET /api/v1/runs/{run_id}/events
Accept: text/event-stream
```

参数

Path 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `run_id` | 是 | string | 提交消息接口返回的运行 ID |

Header 参数：

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `Last-Event-ID` | 否 | integer | 断线重连时传入最后成功处理的 SSE 事件 ID |

首次连接不传 `Last-Event-ID`。SSE 中的 `id` 是当前 run 内递增的事件序号，不是消息 ID。

返回值

响应头：

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

开始生成：

```text
id: 1
event: started
data: {"run_id":"run_901","assistant_message_id":"msg_504"}

```

增量内容：

```text
id: 2
event: delta
data: {"assistant_message_id":"msg_504","delta":"这段代码"}

id: 3
event: delta
data: {"assistant_message_id":"msg_504","delta":"主要负责……"}

```

生成完成：

```text
id: 4
event: completed
data: {"message":{"id":"msg_504","role":"assistant","content":"这段代码主要负责……","status":"completed","created_time":"2026-10-06T02:50:01.123456Z"},"finish_reason":"stop"}

```

生成失败：

```text
id: 4
event: error
data: {"code":"MODEL_REQUEST_FAILED","message":"模型请求失败","retryable":true,"assistant_message_id":"msg_504"}

```

心跳：

```text
: heartbeat

```

服务端在没有文本事件时每 15 秒发送一次心跳。心跳没有事件 ID，不参与重放。

服务端应缓存 run 的 SSE 事件。断线重连时只发送 `Last-Event-ID` 之后的事件。已经结束的 run 至少保留事件 10 分钟；事件过期时返回 HTTP `410 EVENTS_EXPIRED`，GUI 随后重新获取对话内容。

收到 `completed` 或 `error` 后，服务端关闭 SSE 连接。SSE 网络断开本身不会停止 Agent 任务，GUI 应保持发送按钮不可点击并尝试重新连接。

## 错误返回格式

URL

```text
适用于以上所有普通 HTTP 接口
```

参数

无。

返回值

```json
{
  "result": false,
  "data": null,
  "error": {
    "code": "CHAT_NOT_FOUND",
    "message": "对话不存在"
  }
}
```

错误码：

| code | HTTP 状态 | 说明 |
| --- | --- | --- |
| `INVALID_REQUEST` | `400` | JSON 或字段格式错误 |
| `INVALID_PAGE_SIZE` | `400` | `page_size` 超出范围 |
| `CHAT_NOT_FOUND` | `404` | 对话不存在 |
| `RUN_NOT_FOUND` | `404` | run 不存在 |
| `CHAT_BUSY` | `409` | 对话已有未结束的 run |
| `IDEMPOTENCY_CONFLICT` | `409` | 相同幂等键对应不同消息内容 |
| `EVENTS_EXPIRED` | `410` | SSE 事件已超过保留期 |
| `AGENT_UNAVAILABLE` | `503` | Agent 暂时不可用 |
| `MODEL_REQUEST_FAILED` | `500` 或 SSE | 模型调用失败 |
| `INTERNAL_ERROR` | `500` | 未预期的服务端错误 |

本文档 Review 通过后，再同步修改 GUI HTTP 客户端、内存 mock server 和测试。
