"""Session log + Trajectory 的 Pydantic 数据模型。

事件词汇对照 deepseek-harness 的 ``SessionEventMap`` 做精简,
只保留 swift-agent 实际产出的事件类型:

- session_start     - 会话级 metadata(也会作为 header 第一行)
- turn_start        - 一轮对话开始
- system_prompt     - 本轮 supervisor 用的系统提示词(供轨迹视图"System" cell 渲染)
- user_message      - 用户消息
- assistant_chunk   - 单个 token 增量
- assistant_message - 完整 assistant 消息(turn 终止时汇总)
- tool_call         - 工具调用发起
- tool_result       - 工具调用结果
- file_emitted      - 生成的文件(走 SSE file 事件)
- turn_end          - 一轮结束(normal / error / abort)
- session_end       - 会话结束(目前与 turn_end 同步,但保留语义扩展空间)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 文件格式版本(保留升级空间)
SESSION_LOG_FORMAT_VERSION = 1

# 事件类型字面量
SessionEventType = Literal[
    "session_start",
    "turn_start",
    "system_prompt",
    "user_message",
    "assistant_chunk",
    "assistant_message",
    "tool_call",
    "tool_result",
    "file_emitted",
    "turn_end",
    "session_end",
]


class SessionHeader(BaseModel):
    """JSONL 第一行:会话级元信息。

    写入路径::``data/sessions/<session_id>/session.jsonl`` 的第 0 行。
    """

    type: Literal["session"] = "session"
    version: int = SESSION_LOG_FORMAT_VERSION
    id: str
    created_at: float  # unix epoch seconds
    agent_name: str | None = None
    model: str | None = None


class SessionEvent(BaseModel):
    """JSONL 第 N 行(N >= 1):单条事件。

    ``seq`` 由 writer 单调递增分配,前端折叠算法用它做排序兜底。
    """

    seq: int
    time: float  # unix epoch seconds
    type: SessionEventType
    data: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Trajectory 折叠结果(前端消费的对象)
# --------------------------------------------------------------------------- #


class ToolCallStep(BaseModel):
    """一条工具调用的输入输出。"""

    call_id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    is_error: bool = False
    latency_ms: int | None = None


class AssistantStep(BaseModel):
    """一轮 LLM 调用的产物。"""

    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None


class TrajectoryStep(BaseModel):
    """一个 ``(turn, step)`` 对应的折叠步骤。

    - kind=tool: ``tool`` 字段必填
    - kind=assistant_message: ``assistant`` 字段必填
    - kind=file: ``file_meta`` 字段必填
    """

    turn: int
    step: int
    kind: Literal["assistant_message", "tool", "file"]
    started_at: float
    ended_at: float | None = None
    latency_ms: int | None = None
    tool: ToolCallStep | None = None
    assistant: AssistantStep | None = None
    file_meta: dict[str, Any] | None = None


class SystemPromptRecord(BaseModel):
    """一条会话级 system_prompt 事件。

    参考 deepseek-harness 的 ``request/header`` 设计:
    - 只在会话首次 / 真正变化时才追加(不每 turn 重复)
    - UI 把 initial 那条钉在 timeline 顶部,后续 change 按 seq 插入
    """

    seq: int
    time: float
    content: str
    reason: Literal["initial", "change"] = "initial"


class TrajectoryTurn(BaseModel):
    """一轮用户交互:从 user_message 到 turn_end。"""

    turn: int
    started_at: float
    ended_at: float | None = None
    ended_reason: str | None = None  # normal / error / abort
    user_message: str = ""
    steps: list[TrajectoryStep] = Field(default_factory=list)


class TrajectoryToolCallSummary(BaseModel):
    name: str
    count: int
    error_count: int


class TrajectorySummary(BaseModel):
    turns: int
    steps: int
    tool_calls: list[TrajectoryToolCallSummary] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    empty: bool = False  # 当 JSONL 不存在或为空时为 True


class Trajectory(BaseModel):
    """``GET /api/sessions/{id}/trajectory`` 的响应体。"""

    session: SessionHeader
    system_prompts: list[SystemPromptRecord] = Field(default_factory=list)
    turns: list[TrajectoryTurn] = Field(default_factory=list)
    summary: TrajectorySummary