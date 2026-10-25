"""Trajectory + Session log.

学习自 deepseek-harness 的设计:

- **Session log**:每个会话一份追加式 JSONL,首行是 header,后续是
  ``{seq, time, type, data}`` 事件。是会话的**唯一可信源**,
  用于回放 / 调试 / 轨迹可视化。

- **Trajectory**:session log 之上的**只读投影**。``SessionLogReader``
  把 JSONL 折叠成 ``Trajectory``(turns → steps),前端只消费
  折叠后的结构,不直接读 JSONL。

参考 /Users/macbook/deepseek-harness:
- ``packages/core/session/src/types.ts``            — SessionHeader / SessionEvent
- ``packages/session/session-persistence-jsonl``    — JSONL 文件布局 / header / scanner
- ``packages/client/ui-trajectory``                  — 折叠后的 TrajectorySnapshot
"""

from app.trajectory.schema import (
    SessionEvent,
    SessionHeader,
    Trajectory,
    TrajectoryStep,
    TrajectorySummary,
    TrajectoryToolCallSummary,
    TrajectoryTurn,
)
from app.trajectory.log_writer import SessionLogWriter
from app.trajectory.log_reader import SessionLogReader

__all__ = [
    "SessionEvent",
    "SessionHeader",
    "Trajectory",
    "TrajectoryStep",
    "TrajectorySummary",
    "TrajectoryToolCallSummary",
    "TrajectoryTurn",
    "SessionLogWriter",
    "SessionLogReader",
]