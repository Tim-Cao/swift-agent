"""Supervisor package。

v11:不再有硬编码的 supervisor 单例 —— agent 全部由 DB 驱动,
运行时按记录动态构建(见 app/services/agent_service.py)。
"""

from app.supervisor.thread import make_thread_config

__all__ = ["make_thread_config"]
