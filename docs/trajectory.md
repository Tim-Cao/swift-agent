# Trajectory 实现文档

> 版本:v9 起,v11.4 随「会话轨迹视图」重做前端布局(双栏 Tab,不再是抽屉)
> 状态:已合并到 `dev`
> 参考:`deepseek-harness` `packages/core/session` + `packages/client/ui-trajectory`

---

## 目录

- [1. 目标与设计动机](#1-目标与设计动机)
- [2. 整体架构](#2-整体架构)
- [3. 工作流程](#3-工作流程)
- [4. 数据结构](#4-数据结构)
- [5. 写入路径:SessionLogWriter](#5-写入路径sessionlogwriter)
- [6. 折叠算法:SessionLogReader](#6-折叠算法sessionlogreader)
- [7. API](#7-api)
- [8. 前端组件](#8-前端组件)
- [9. 配置](#9-配置)
- [10. 测试](#10-测试)
- [11. 已知边界与扩展点](#11-已知边界与扩展点)

---

## 1. 目标与设计动机

提供"会话级轨迹视图",把对话过程的完整细节(token 级流式、工具调用、文件产物、系统提示词)在会话进行中和结束后都能可视化回看。

参考 deepseek-harness 的两层抽象:

| 抽象 | 角色 | 落盘? | 消费者 |
|---|---|---|---|
| **Session log** | 会话**唯一可信源**,顺序事件流 | 是(JSONL) | 调试 / 回放 / 后端 |
| **Trajectory** | session log 之上的**只读投影** | 否 | 前端 UI |

两层分离的好处:
- 写入路径是简单的 append + fsync,出错不影响业务库(SQLite)
- 前端消费折叠后的 `Trajectory`,不直接解析 JSONL,折叠逻辑可以迭代优化
- 日志是 line-delimited JSON,可以直接 `tail -f`、`jq`、导入其他分析工具

---

## 2. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3)                                                  │
│  ┌──────────────┐    polling      ┌──────────────────────────┐    │
│  │ TrajectoryView│──────────────▶│ getTrajectory()            │    │
│  │ (timeline +   │   1.5s/5s     │ exportSessionLog()         │    │
│  │  details      │◀──────────────│                            │    │
│  │  panel)       │  Trajectory   └──────────────────────────┘    │
│  └──────────────┘  (folded)                                       │
│         ▲                                                          │
│         │ user click                                               │
│         ▼                                                          │
│  ┌──────────────────────────┐                                     │
│  │ TrajectoryDetailsPanel   │  右侧抽屉,渲染选中 cell 详情        │
│  │ TrajectoryStepItem       │  单行 cell(32px,kind tag)          │
│  └──────────────────────────┘                                     │
└────────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/JSON
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                                 │
│  ┌──────────────────┐  ┌─────────────────────────────────────┐    │
│  │ routes/trajectory │  │ GET /sessions/{id}/trajectory        │    │
│  │                  │  │ GET /sessions/{id}/log/export        │    │
│  └──────────────────┘  └─────────────────────────────────────┘    │
│         │                            │                            │
│         ▼                            ▼                            │
│  ┌──────────────────┐  ┌─────────────────────────────────────┐    │
│  │ SessionLogReader │  │ SessionLogWriter(只 chat_service 用) │    │
│  │  折叠成 Trajectory│  │  append events + fsync              │    │
│  └──────────────────┘  └─────────────────────────────────────┘    │
│         │                            │                            │
│         ▼                            ▼                            │
│  data/sessions/<sid>/session.jsonl  (single source of truth)     │
└────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ raw events
                              │
┌────────────────────────────────────────────────────────────────────┐
│  chat_service.stream_chat()                                        │
│  - 把 astream_events 旁路写进 log                                  │
│  - 同一路径照常产 SSE (token/file/done/error)                       │
└────────────────────────────────────────────────────────────────────┘
```

关键边界:
- **写入路径只追加,从不改写历史**(`open(append)` + per-session `asyncio.Lock`)
- **SSE 契约不变**(v8.4 之后是 `token/file/done/error` 四事件,trajectory 是旁路)
- **Reader 是纯函数式**(`_fold_*` 函数不依赖 IO,可单测)

---

## 3. 工作流程

### 3.1 用户发消息 → JSONL 落盘

```
用户消息  ──┐
            ▼
   POST /api/chat   ──▶  stream_chat()
                              │
                              ├─▶ repo.append_message(...)        (业务库)
                              │
                              ├─▶ log_writer.open(...)           (创建/续写 JSONL)
                              │     └─▶ 首次:写 header
                              │     └─▶ 已存在:从磁盘 sync max seq
                              │
                              ├─▶ log_writer.append("system_prompt", ...)  (仅首次)
                              ├─▶ log_writer.append("turn_start", ...)
                              ├─▶ log_writer.append("user_message", ...)
                              │
                              ├─▶ agent.astream_events(...)
                              │     │
                              │     ├─▶ _log_raw_event(...)      (写 JSONL)
                              │     │     ├─ assistant_chunk    (delta)
                              │     │     ├─ assistant_message  (完整 content + usage)
                              │     │     ├─ tool_call
                              │     │     └─ tool_result
                              │     │
                              │     └─▶ _map_event(...)          (产 SSE token/file)
                              │
                              ├─▶ log_writer.append("turn_end", {reason})
                              └─▶ log_writer.close()
```

### 3.2 前端轮询 → 折叠渲染

```
切到 trajectory tab
   │
   ▼
TrajectoryView 挂载,watch([sid, active, isStreaming])
   │
   ▼
startPoll(sid, isStreaming?)
   ├─ streaming=true  → setInterval(1500ms)
   └─ streaming=false → setInterval(5000ms)
   │
   ▼ (每次 tick)
   getTrajectory(sid)
       │
       ▼
   GET /api/sessions/{sid}/trajectory
       │
       ▼
   SessionLogReader.read()
       ├─▶ read_header()      → SessionHeader
       ├─▶ read_events()      → [SessionEvent, ...]
       ├─▶ _fold_system_prompts(events)
       ├─▶ _fold_to_turns(events)
       └─▶ _build_summary(turns)
       │
       ▼
   Trajectory Pydantic 模型 → JSON → 前端
       │
       ▼
   timelineItems computed  (把 turns + system_prompts 扁平化排序)
       │
       ▼
   .timeline 渲染  +  选中 cell → .details-pane 抽屉
```

### 3.3 实时性边界

| 场景 | 轮询间隔 | 是否触发即时刷新 |
|---|---|---|
| trajectory tab 不可见 | 不轮询 | — |
| 可见 + 流式中 | 1500ms | 是(每个 token 约 1.5s 内可见) |
| 可见 + 流结束 | 5000ms | 否(用户已切到 trajectory tab,无需立即刷新) |
| 切走 tab / 换会话 | 立即 `clearPoll()` | — |

**为什么不推送?** 项目后端 SSE 只在 `chat` 流期间存在,流结束后连接就断。要做实时只能 WebSocket,代价是引入独立通道且需要服务端内存中保留 session 状态。当前架构选择 polling,边界场景(典型 UX 是"用户发完消息切到 trajectory tab 看过程")覆盖率足够。

---

## 4. 数据结构

### 4.1 文件布局

```
backend/data/sessions/<session_id>/session.jsonl
```

第 0 行是 header,后续每行一条事件。

### 4.2 Header(第 0 行)

```json
{
  "type": "session",
  "version": 1,
  "id": "<session_id>",
  "created_at": 1700000000.123,
  "agent_name": null,
  "model": "gpt-4o-mini"
}
```

`SESSION_LOG_FORMAT_VERSION = 1`,保留升级空间。

### 4.3 事件 schema

```python
class SessionEvent(BaseModel):
    seq: int               # 单调递增(从 1 开始)
    time: float            # unix epoch seconds
    type: SessionEventType
    data: dict[str, Any]
```

### 4.4 事件词汇表

| `type` | `data` 字段 | 触发点 | 备注 |
|---|---|---|---|
| `session_start` | — | (保留) | 目前不用,header 已带元信息 |
| `turn_start` | `{"turn": N}` | `chat_service.stream_chat` 进入新轮 | N 由 `next_turn_index()` 计算,接续已有 JSONL |
| `system_prompt` | `{"content": str, "reason": "initial"\|"change"}` | 仅当 `was_empty_on_open=True`(首条) | 后续 prompt 切换写 `change`,当前实现固定 `initial` |
| `user_message` | `{"content": str}` | 收到用户消息后立即 | 原始内容,不带 `[UPLOAD_DIR:...]` 前缀 |
| `assistant_chunk` | `{"turn": N, "step": K, "delta": str}` | 每次 `_log_raw_event` 收到 `on_chat_model_stream` | delta 是 token 增量 |
| `assistant_message` | `{"turn": N, "step": K, "content": str, "usage": {input_tokens, output_tokens}}` | `on_chat_model_end` | 完整内容 + 用量;Reader 优先用这个替换 chunk 拼接结果 |
| `tool_call` | `{"turn": N, "step": K, "call_id": str, "name": str, "input": dict}` | `on_tool_start` | call_id = LangGraph run_id |
| `tool_result` | `{"turn": N, "step": K, "call_id": str, "name": str, "output": str, "is_error": bool}` | `on_tool_end` | output 是 string 归一化后的 |
| `file_emitted` | `{"turn": N, "url": str, "filename": str, "mime": str, "size_bytes": int}` | `_detect_file_event` 扫到 xlsx 路径 | 与 SSE `file` 事件同源 |
| `turn_end` | `{"turn": N, "reason": "normal"\|"error"\|"aborted"}` | 流结束 / 异常 / `asyncio.CancelledError` | 实时轮询场景下若没收到 → `ended_reason=None`(标识进行中) |
| `session_end` | — | (废弃) | 早期每 turn 误写过;Reader 已忽略 |

### 4.5 折叠后的 Trajectory 模型

```python
class Trajectory(BaseModel):
    session: SessionHeader
    system_prompts: list[SystemPromptRecord]    # session-level,不进 turn
    turns: list[TrajectoryTurn]
    summary: TrajectorySummary

class TrajectoryTurn(BaseModel):
    turn: int
    started_at: float
    ended_at: float | None = None
    ended_reason: str | None = None             # 进行中 → None
    user_message: str = ""
    steps: list[TrajectoryStep]                 # 排序后 + 重新编号

class TrajectoryStep(BaseModel):
    turn: int
    step: int                                    # 0-based,按 started_at 重排
    kind: Literal["assistant_message", "tool", "file"]
    started_at: float
    ended_at: float | None = None
    latency_ms: int | None = None
    tool: ToolCallStep | None = None
    assistant: AssistantStep | None = None
    file_meta: dict | None = None

class TrajectorySummary(BaseModel):
    turns: int
    steps: int
    tool_calls: list[{name, count, error_count}]    # 按 name 排序
    total_input_tokens: int
    total_output_tokens: int
    empty: bool                                       # JSONL 不存在 → True
```

### 4.6 完整示例 JSONL

```jsonl
{"type":"session","version":1,"id":"abc123","created_at":1700000000.0,"agent_name":null,"model":"gpt-4o-mini"}
{"seq":1,"time":1700000000.5,"type":"system_prompt","data":{"content":"你是 Swift Agent...","reason":"initial"}}
{"seq":2,"time":1700000001.0,"type":"turn_start","data":{"turn":0}}
{"seq":3,"time":1700000001.1,"type":"user_message","data":{"content":"分析销售表"}}
{"seq":4,"time":1700000002.0,"type":"assistant_chunk","data":{"turn":0,"step":0,"delta":"好的"}}
{"seq":5,"time":1700000002.3,"type":"assistant_chunk","data":{"turn":0,"step":0,"delta":",我来"}}
{"seq":6,"time":1700000002.8,"type":"tool_call","data":{"turn":0,"step":1,"call_id":"run_xxx","name":"execute_pandas_code","input":{"code":"df.head()"}}}
{"seq":7,"time":1700000003.1,"type":"tool_result","data":{"turn":0,"step":1,"call_id":"run_xxx","name":"execute_pandas_code","output":"   销售  数量\n0  A  100","is_error":false}}
{"seq":8,"time":1700000003.5,"type":"assistant_message","data":{"turn":0,"step":0,"content":"好的,我来","usage":{"input_tokens":150,"output_tokens":4}}}
{"seq":9,"time":1700000004.0,"type":"file_emitted","data":{"turn":0,"url":"/api/downloads/abc123/result.xlsx","filename":"result.xlsx","mime":"...","size_bytes":12345}}
{"seq":10,"time":1700000004.1,"type":"turn_end","data":{"turn":0,"reason":"normal"}}
```

折叠后:

```json
{
  "session": {"id": "abc123", "created_at": 1700000000.0, "model": "gpt-4o-mini", ...},
  "system_prompts": [{"seq": 1, "reason": "initial", "content": "你是 Swift Agent..."}],
  "turns": [{
    "turn": 0, "started_at": 1700000001.0, "ended_at": 1700000004.1, "ended_reason": "normal",
    "user_message": "分析销售表",
    "steps": [
      {"step": 0, "kind": "assistant_message", "assistant": {"content": "好的,我来", "input_tokens": 150, "output_tokens": 4}},
      {"step": 1, "kind": "tool", "tool": {"name": "execute_pandas_code", "input": {"code": "df.head()"}, "output": "...", "is_error": false}},
      {"step": 2, "kind": "file", "file_meta": {"url": "/api/downloads/abc123/result.xlsx", "filename": "result.xlsx", ...}}
    ]
  }],
  "summary": {"turns": 1, "steps": 3, "tool_calls": [{"name": "execute_pandas_code", "count": 1, "error_count": 0}], "total_input_tokens": 150, "total_output_tokens": 4, "empty": false}
}
```

---

## 5. 写入路径:SessionLogWriter

### 5.1 关键设计

| 设计点 | 说明 |
|---|---|
| 同步 fsync | 每条事件 `flush + os.fsync`,数据量小(单轮 ~10-100 行)开销可忽略,SSE 流结束即代表日志已落盘 |
| per-session `asyncio.Lock` | 防止前端双击发送 / 并发 stream 写穿同一文件 |
| 一次性 header | `open()` 时若 `tell() == 0` 写 header;否则 sync `_seq` 接续计数 |
| Append-only | 文件用 `"a"` 模式,从不 truncate / rewrite |
| JSON 兜底 | `_json_default` 处理 LangChain Message / Pydantic 对象 |

### 5.2 关键 API

```python
writer = SessionLogWriter(session_id, root=Path("./data/sessions"))

await writer.open(agent_name="supervisor", model="gpt-4o-mini")
# open 时若文件已存在,_seq 自动从磁盘 sync;was_empty_on_open 标记是否首次

await writer.append("turn_start", {"turn": 0})             # 返回 SessionEvent(seq, time, type, data)
await writer.append("user_message", {"content": "hi"})
await writer.append("turn_end", {"turn": 0, "reason": "normal"})

turn_index = await writer.next_turn_index()                # 多轮:接续已有 turn 号

await writer.close()
```

### 5.3 失败兜底

- **CancelledError**(客户端断连):`chat_service` 在 `except asyncio.CancelledError` 里补写 `turn_end(reason="aborted")`,`finally` 关闭句柄
- **业务异常**:`turn_end(reason="error")`
- **正常结束**:`turn_end(reason="normal")`
- **进程崩溃 / 异常中断**:没收到 `turn_end`,Reader 仍能折叠,但 `ended_reason = None`(标识"进行中",前端不显示错误态)

---

## 6. 折叠算法:SessionLogReader

### 6.1 阶段

```
events: list[SessionEvent]
   │
   ├─▶ _fold_system_prompts(events)
   │     └─▶ list[SystemPromptRecord]
   │
   ├─▶ _fold_to_turns(events)
   │     ├─ 状态机按 turn_start / user_message / assistant_* / tool_* / file / turn_end
   │     ├─ 累积 assistant_acc[(turn, step)] → content + usage
   │     ├─ 累积 pending_tool[call_id] → 输入 / 输出
   │     ├─ file_emitted → 独立 step
   │     ├─ turn_end → _flush_steps
   │     └─ 兜底:无 turn_end 也 flush(保留 ended_reason=None)
   │
   └─▶ _build_summary(turns)
         └─▶ TrajectorySummary
```

### 6.2 关键算法点

#### 6.2.1 Turn 编号重新计

`_fold_to_turns` **不读 JSONL 的 `turn` 字段**,而是从 `turn_start` 出现顺序递增编号(0, 1, 2, ...)。

理由:早期 `chat_service` 硬编码 `turn=0` 写入历史数据,多轮对话全打成 turn 0 会让前端无法区分。重新计可兼容老 JSONL。

#### 6.2.2 system_prompt 去重

`_fold_system_prompts` 按 `headerEquals` 思路折叠:**相邻 content 相同的合并成一条**。

- 新版 `chat_service` 只写 `initial` / `change`,本来就只有 1-2 条
- 老版每 turn 重复写 system_prompt,Reader 折叠成 1 条
- 防御性兜底:即使 `chat_service` 写盘逻辑失效,UI 不会显示重复 system cell

#### 6.2.3 Steps 排序 + 重编号

`_flush_steps(turn, assistant_acc, pending_tool)`:

1. 把 turn 已有 steps(理论上不会有)与新生成的合并
2. 按 `(started_at, kind)` 排序——assistant 平局优先(符合"LLM 触发工具"的因果直觉)
3. 清空原列表,按新顺序塞回,`step` 字段从 0 重新编号

理由:assistant → tool → assistant 的因果顺序保留,且 `step` 字段单调递增不会冲突。

#### 6.2.4 进行中 turn 不标 aborted

```python
# 旧实现
if current is not None:
    _flush_steps(...)
    current.ended_reason = current.ended_reason or "aborted"  # ← 坑

# 现实现
if current is not None:
    _flush_steps(...)  # ended_reason 留 None
```

理由:实时轮询场景下,turn 进行中没收到 `turn_end` 是常态,标 `aborted` 会让前端误把进行中的 turn 渲染成已中断。真正的 abort 是 `chat_service` 显式写 `turn_end(reason="aborted")` 走到的路径。

### 6.3 关键 API

```python
reader = SessionLogReader(session_id, root=Path("./data/sessions"))

header = await reader.read_header()           # None / SessionHeader
events = await reader.read_events()           # [] / [SessionEvent, ...]
trajectory = await reader.read()              # 完整 Trajectory
raw = await reader.read_raw_bytes()           # bytes,用于 /log/export 下载
```

---

## 7. API

### 7.1 `GET /api/sessions/{session_id}/trajectory`

返回折叠后的 `Trajectory`(Pydantic 模型 → JSON)。

| 状态码 | 含义 |
|---|---|
| 200 | 正常(可能 `summary.empty=true`,JSONL 不存在) |
| 404 | session_id 在业务库(SQLite)不存在 |

响应示例(简化):

```json
{
  "session": {"id": "...", "created_at": 1700000000.0, "model": "gpt-4o-mini", "agent_name": null},
  "system_prompts": [{"seq": 1, "time": ..., "content": "...", "reason": "initial"}],
  "turns": [...],
  "summary": {"turns": 1, "steps": 3, "tool_calls": [...], "total_input_tokens": 150, "total_output_tokens": 4, "empty": false}
}
```

### 7.2 `GET /api/sessions/{session_id}/log/export`

返回原始 JSONL 字节流,触发浏览器下载。

| Header | 值 |
|---|---|
| `Content-Type` | `application/x-ndjson` |
| `Content-Disposition` | `attachment; filename="session-<id>.jsonl"` |
| `X-Session-Id` | `<id>` |

| 状态码 | 含义 |
|---|---|
| 200 | 正常(可能 body 为空,JSONL 尚未落盘) |
| 404 | session_id 在业务库不存在 |

前端通过 `<a download>` 标签触发,不走 axios(避免大文件 base64 转码)。

---

## 8. 前端组件

### 8.1 组件树

```
ChatWindow.vue
  └─ TrajectoryView.vue           (双栏布局)
       ├─ .timeline-pane           (左侧,可滚动)
       │    ├─ trajectory-header  (元信息 + summary + 工具调用统计 + 刷新/下载按钮)
       │    └─ .timeline
       │         ├─ .turn-divider (Turn N + 角标 + 顶部 2px 细线)
       │         ├─ TrajectoryStepItem (单行 cell,32px)
       │         │    └─ kind tag (assistant=紫 / tool=蓝 / file=绿 / system=灰 / user=青)
       │         └─ TrajectoryDetailsPanel 触发:row.click → selectedCell
       │
       └─ .details-pane            (右侧,常驻抽屉)
            └─ TrajectoryDetailsPanel.vue   (按 cell.kind 渲染)
                 ├─ system: prompt pre + 文本内容
                 ├─ user-message: MarkdownView
                 ├─ tool: input JSON + output + 错误 badge + latency
                 ├─ assistant: MarkdownView + token + latency
                 └─ file: 文件名 + size + url
```

### 8.2 关键交互

#### 选中态管理

```js
const selectedCell = ref(null)  // 单选

function selectCell(item) {
  // 切换语义:再点同一 cell → 取消;点不同 cell → 切换
  if (selectedCell.value && getCellId(selectedCell.value) === getCellId(item)) {
    selectedCell.value = null
  } else {
    selectedCell.value = item
  }
}
```

#### 选中行视觉

```css
.step-row.is-selected {
  background: #ecf5ff;           /* 浅蓝高亮 */
  box-shadow: inset 3px 0 0 #409eff;  /* 左侧 3px 蓝色 rail */
}
```

#### 实时轮询

```js
const POLL_INTERVAL_STREAMING_MS = 1500
const POLL_INTERVAL_IDLE_MS = 5000

watch(
  [() => props.sessionId, () => props.active, isStreaming],
  ([sid, active, streaming]) => {
    clearPoll()
    if (!sid || !active) return
    startPoll(sid, streaming)  // 立即起一次
  },
  { immediate: true },
)

onUnmounted(() => clearPoll())
```

#### Empty state

- 早期会话没有 JSONL → 显示 `<el-empty>` + "刷新" / "下载原始 JSONL" 两个按钮
- 独立 `GET` 拉数据(不依赖 polling)

### 8.3 timelineItems 扁平化算法

```js
const timelineItems = computed(() => {
  // 把 system_prompts 跟 turns 合并成扁平事件序列:
  // - system_prompts 按 time 落到对应 turn 第一行之前
  // - initial 自然出现在 turn 0 之前
  // - firstOfTurn 永远只给该 turn 第一个非 system cell
  //   (user_message 优先,无 user_message 时第一个 step 兜底)
  // 这样 Turn N 角标 + 顶部 2px 细线总是落在 user 行,而不是 system 行
})
```

---

## 9. 配置

### 9.1 `AppSettings`

```python
# backend/app/core/config.py
trajectory_log_dir: str = "./data/sessions"   # JSONL 落盘根目录
trajectory_log_enabled: bool = True           # 总开关(预留)
```

`lifespan` 在启动时 `mkdir(parents=True, exist_ok=True)` 创建根目录。

### 9.2 前端无新增配置

轮询间隔在 `TrajectoryView.vue` 内常量定义,无需外部注入。

---

## 10. 测试

### 10.1 后端单元测试(`backend/tests/test_trajectory.py`)

19 个测试,覆盖:

- **Writer**:写 header / seq 单调递增 / 续写不重写 header / was_empty_on_open 标记
- **Reader 折叠**:单 turn assistant / tool_call 配对 / error turn / 缺失文件 / step 排序 / system_prompt session-level 折叠 / system_prompt change 保留历史 / 老 JSONL 无 system_prompt 兼容 / reader 兜底去重 / reader 保留变化 prompt
- **Reader 边界**:进行中 turn `ended_reason = None`(回归测试,防止有人重新引入自动标 `aborted`)
- **API 端点**:404 / 200 empty / 200 log/export / round-trip

### 10.2 运行

```bash
cd backend && uv run pytest tests/test_trajectory.py -v
```

---

## 11. 已知边界与扩展点

### 11.1 已知边界

| 场景 | 行为 |
|---|---|
| 进程崩溃 / 异常中断 | 没收到 `turn_end`,Reader 仍折叠,`ended_reason=None`,前端显示进行中(不显示 error) |
| 客户端断连(CancelledError) | 兜底写 `turn_end(reason="aborted")` |
| 老 JSONL(每 turn 重复写 system_prompt) | Reader 自动去重成 1 条 |
| 老 JSONL(硬编码 turn=0) | Reader 重新计 turn 编号 |
| 超大 JSONL(>10MB) | Reader 一次性 `read_events` 全量读;可改为流式折叠(待扩展) |
| 超长 tool output(>10MB) | 写盘无截断,可能撑爆;待加 max_output_bytes 截断 |
| 多个流同时写同一 session | `asyncio.Lock` 串行化,后到的等前面的写完 |

### 11.2 扩展点

1. **WebSocket 实时推送**:把 polling 替换成 WebSocket,服务端在 `append()` 后推送 diff;需要服务端保留 in-memory session 状态
2. **System prompt 动态切换**:当前 `chat_service` 固定写 `initial`,可在 supervisor prompt 变化时写 `change`
3. **结构化工具输入/输出渲染**:tool.input 可能是嵌套 dict,目前直接 JSON.stringify;可对 `execute_pandas_code` 的 `code` 字段做语法高亮
4. **Diff 视图**:deepseek-harness 有 system prompt update diff;可以做
5. **回放功能**:目前只有"下载原始 JSONL",可加"从 JSONL 重放对话"按钮
6. **导出 HTML / PDF**:JSONL → Trajectory → 静态 HTML,方便分享

---

## 附录 A:相关文件清单

### 后端

- `backend/app/trajectory/__init__.py` — 模块导出
- `backend/app/trajectory/schema.py` — Pydantic 数据模型
- `backend/app/trajectory/log_writer.py` — JSONL 写入器
- `backend/app/trajectory/log_reader.py` — JSONL 读取 + 折叠
- `backend/app/api/routes/trajectory.py` — `GET trajectory` + `GET log/export`
- `backend/app/api/routes/__init__.py` — 注册 trajectory router
- `backend/app/core/config.py` — `trajectory_log_dir` / `trajectory_log_enabled`
- `backend/app/core/lifespan.py` — 启动时建 log 目录
- `backend/app/services/chat_service.py` — `stream_chat` 旁路写 log + `_log_raw_event`
- `backend/tests/test_trajectory.py` — 19 个测试

### 前端

- `frontend/src/api/trajectory.js` — `getTrajectory` / `exportSessionLog`
- `frontend/src/components/TrajectoryView.vue` — 双栏布局 + polling
- `frontend/src/components/TrajectoryStepItem.vue` — 单行 cell 渲染
- `frontend/src/components/TrajectoryDetailsPanel.vue` — 右侧详情面板
- `frontend/src/components/ChatWindow.vue` — trajectory tab 容器

### 配置

- `.gitignore` — `backend/reports/` / `allure-results/` / `allure-report/`(测试报告产物不提交)

---

## 附录 B:关键事件对照 deepseek-harness

| deepseek-harness | swift-agent | 差异 |
|---|---|---|
| `SessionEventMap` 几十种事件 | 11 种精简事件 | 我们只用 supervisor(无 multi-agent 子会话),合并相似事件 |
| `step/start` + `step/end` 包裹 | 直接 `(turn, step)` 二元组 | 简化层数,Reader 按自然边界切 |
| `headerEquals` 做 prompt dedupe | `_fold_system_prompts` 同样思路 | 完全对齐 |
| `request/header` 把 prompt 钉顶部 | `Trajectory.system_prompts` 顶层字段 | 完全对齐 |
| `TrajectorySnapshotBuilder` 折叠 | `_fold_to_turns` + `_build_summary` | 命名 / 字段对齐 |
| `/api/session.export` 返回 ZIP | `/api/sessions/{id}/log/export` 返回单 JSONL | 无子会话,不需要 ZIP |
| WebSocket 实时推送 | Polling(1.5s streaming / 5s idle) | 渐进式实现,polling 边界足够 |
