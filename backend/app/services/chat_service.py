"""聊天业务:组装消息、调用 supervisor、流式产出前端 SSE 契约事件。

v5 改动:
  - input 是 delta:只传本轮新增的 [HumanMessage(content=user_message)],
    不再从业务库加载历史、不再拼全量 messages。
  - 历史 messages 由 LangGraph loop 启动时 channels_from_checkpoint
    从 checkpointer 还原,然后 deepagents 的 DeltaChannel._messages_delta_reducer
    按 message.id 去重合并(DeepAgentState.messages: DeltaChannel)。
  - 不传全量 messages 是为了避免 ensure_message_ids 给老消息赋新 UUID,
    污染 checkpoint ID 链,扰乱 tool_call↔tool_message 配对与 summarization tombstone。
  - 业务库(SQLite)与 checkpointer 是两个独立层:业务库存审计/展示,
    checkpointer 存图运行时 state;两者通过 session_id 关联。

v8.10 改动:
  - 捕获异常时区分"上游 LLM provider 临时错误"和"业务错误":
    上游 5xx / 网络断 / 超时 → 给前端友好提示"上游 LLM 服务暂时不可用,请稍后重试";
    业务错误保持原样
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.services.session_service import (
    create_default_session,
    rename_if_first_user_message,
)
from app.supervisor.builder import get_supervisor, make_thread_config

logger = logging.getLogger(__name__)


def _classify_stream_error(e: BaseException) -> dict[str, Any]:
    """把 stream_chat 抛出的异常分类成 {code, user_message, log_level}。

    v8.10:
      - provider 5xx (openai.InternalServerError) → user-friendly 重试提示
      - provider 网络/超时 (APIConnectionError / APITimeoutError) → 同上
      - provider 4xx (RateLimitError / BadRequestError 等) → 保留原 message 但加前缀
      - 业务错误 / 其它 → 保留原 message
    """
    # 1) 尝试导入 openai 的异常类型(没装也不影响)
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )
    except ImportError:
        APIConnectionError = APITimeoutError = APIStatusError = None  # type: ignore
        InternalServerError = RateLimitError = None  # type: ignore

    # 2) 优先按 type 匹配
    name = type(e).__name__

    if InternalServerError is not None and isinstance(e, InternalServerError):
        return {
            "code": "provider_5xx",
            "user_message": "上游 LLM 服务暂时不可用(500),请稍后重试",
            "log_level": "warning",
        }
    if APITimeoutError is not None and isinstance(e, APITimeoutError):
        return {
            "code": "provider_timeout",
            "user_message": "上游 LLM 服务连接超时,请稍后重试",
            "log_level": "warning",
        }
    if APIConnectionError is not None and isinstance(e, APIConnectionError):
        return {
            "code": "provider_connection",
            "user_message": "上游 LLM 服务网络不通,请稍后重试",
            "log_level": "warning",
        }
    if RateLimitError is not None and isinstance(e, RateLimitError):
        return {
            "code": "provider_rate_limit",
            "user_message": "上游 LLM 调用频率超限,请稍候再试",
            "log_level": "warning",
        }
    # 3) 字符串兜底匹配(避免漏掉某种 SDK 包装层)
    s = str(e).lower()
    # "internal server error" / "internalservererror" / "server_error" 等
    if "500" in s and ("internal server" in s or "internalserver" in s or "server_error" in s):
        return {
            "code": "provider_5xx",
            "user_message": "上游 LLM 服务暂时不可用(500),请稍后重试",
            "log_level": "warning",
        }
    if "timeout" in s or "timed out" in s:
        return {
            "code": "provider_timeout",
            "user_message": "上游 LLM 服务连接超时,请稍后重试",
            "log_level": "warning",
        }
    if ("connection" in s or "connect" in s) and ("error" in s or "reset" in s or "refused" in s):
        return {
            "code": "provider_connection",
            "user_message": "上游 LLM 服务网络不通,请稍后重试",
            "log_level": "warning",
        }
    if "rate limit" in s or "rate_limit" in s or "429" in s:
        return {
            "code": "provider_rate_limit",
            "user_message": "上游 LLM 调用频率超限,请稍候再试",
            "log_level": "warning",
        }

    # 4) 业务/未知错误 → 原样
    return {
        "code": "internal",
        "user_message": str(e),
        "log_level": "exception",
    }


async def ensure_session(
    db: AsyncSession, session_id: str | None, agent_name: str | None
) -> tuple[str, bool]:
    """确保有可用 session,返回 (session_id, 是否新建)。"""
    if session_id:
        existing = await repo.get_session(db, session_id)
        if existing is not None:
            return session_id, False
    new = await create_default_session(db, agent_name=agent_name)
    return new.id, True


async def stream_chat(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    upload_dir: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """流式生成前端 SSE 契约事件(后由 chat.py 渲染为 SSE 行)。

    事件 schema:
      - {"event": "token",      "data": {"content": "<incr>"}}
      - {"event": "tool_call",  "data": {"name": "...", "input": {...}}}
      - {"event": "tool_result","data": {"name": "...", "output": "..."}}
      - {"event": "file",       "data": {"url": "...", "filename": "...", "mime": "..."}}
      - {"event": "done",       "data": {"session_id": "..."}}
      - {"event": "error",      "data": {"message": "..."}}

    upload_dir: 若前端附带(/api/uploads 返回的 upload_dir),会作为
      [UPLOAD_DIR:...] 前缀加到 message 里,让 supervisor 识别为 Excel 流水线。
    """
    # 0. 若有 upload_dir,加 [UPLOAD_DIR:...] 前缀
    llm_message = user_message
    if upload_dir and "[UPLOAD_DIR:" not in user_message:
        llm_message = f"[UPLOAD_DIR:{upload_dir}] {user_message}"

    # 1. 业务库持久化用户消息 + 触发重命名(用原始 user_message,不带前缀)
    await repo.append_message(db, session_id=session_id, role="user", content=user_message)
    await rename_if_first_user_message(db, session_id, user_message)
    await db.commit()

    # 2. 调用 supervisor:input 只传本轮增量 user message。
    #    历史 messages 由 LangGraph 从 checkpointer 还原 + deepagents 的
    #    DeltaChannel._messages_delta_reducer 按 ID 去重合并。
    agent = get_supervisor()
    config = make_thread_config(session_id)
    delta_input = {"messages": [HumanMessage(content=llm_message)]}

    full_text_parts: list[str] = []
    file_emitted = False
    file_attachments: list[dict[str, Any]] = []  # v8.14:累积待持久化的附件
    try:
        # v8.12:提高递归上限从默认 25 → 50,避免 Excel pipeline 串行
        # 调度子 Agent 时 25 个 graph node 不够用(IntakeAgent → RuleParserAgent
        # → DataProcessingAgent → ExcelWriterAgent 一轮大约 8-12 个 node,
        # 连续重试 2-3 轮就会 GraphRecursionError)
        stream_config = {**config, "recursion_limit": 50}
        async for raw in agent.astream_events(
            delta_input,
            config=stream_config,
            version="v2",
        ):
            mapped = _map_event(raw)
            if mapped is None:
                continue
            _collect_text(mapped, full_text_parts)
            # v8.6:从累积的 assistant 文本里检测 xlsx 路径 → 发 file 事件
            # (之前检测 tool_result 事件,但 v8.4 把 tool_result 静默了,触发条件
            # 永远不满足 → file 事件不发 → 前端没有下载按钮)。
            # LLM 完成任务后会在回复里写"saved to /tmp/swift-agent/.../result.xlsx",
            # 这里每收到一个 token 就扫一次,首个匹配的文件立刻发 file 事件。
            if not file_emitted:
                accumulated = "".join(full_text_parts)
                file_evt = _detect_file_event(accumulated, session_id)
                if file_evt:
                    yield file_evt
                    # v8.14:把附件的 data 收集起来,流结束后跟 assistant 文本
                    # 一起落库 → 页面刷新后 / 前端重启后 MessageBubble 仍能
                    # 渲染出下载按钮(否则附件只活在流期间,刷新就丢)
                    file_attachments.append(file_evt["data"])
                    file_emitted = True
            yield mapped
    except Exception as e:  # noqa: BLE001
        classified = _classify_stream_error(e)
        # v8.10:provider 临时错误只记 warning(预期会自愈),不刷 exception
        if classified["log_level"] == "warning":
            logger.warning(
                "stream failed (provider transient): code=%s err=%s",
                classified["code"], e,
            )
        else:
            logger.exception("stream failed")
        yield {
            "event": "error",
            "data": {
                "message": classified["user_message"],
                "code": classified["code"],
            },
        }

    # 兜底:如果到流结束都没在文本里扫到 xlsx 路径(可能 LLM 没明说,
    # 但 write_excel 实际生成了文件),试着扫一下完整文本的最后一遍
    if not file_emitted:
        full_text = "".join(full_text_parts)
        file_evt = _detect_file_event(full_text, session_id)
        if file_evt:
            yield file_evt
            # v8.14:同样收集
            file_attachments.append(file_evt["data"])
            file_emitted = True

    # 3. 业务库持久化 assistant 回复 + 发送 done
    # v8.14:即便没有 text,只要有附件也要落 assistant 消息(否则附件找不到
    # 归属的 message row,前端刷新后 list_messages 拿不到附件元信息)。
    full_text = "".join(full_text_parts)
    if full_text or file_attachments:
        meta = {"attachments": file_attachments} if file_attachments else None
        await repo.append_message(
            db,
            session_id=session_id,
            role="assistant",
            content=full_text,
            meta=meta,
        )
        await db.commit()
    yield {"event": "done", "data": {"session_id": session_id}}


# --------------------------------------------------------------------------- #
# 事件映射
# --------------------------------------------------------------------------- #


def _map_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """把 deepagents 原生 astream_events(v2) 事件映射为前端 SSE 契约。

    v8.4 简化:只对外暴露 token / file / done / error 四类事件。
    - on_tool_start / on_tool_end(对应 tool_call / tool_result)静默掉——
      前端用不到。v8.6 起,file 事件由 stream_chat 扫描累积的 assistant
      文本产生,不再依赖 tool_result 事件。
    - on_chain_start / on_chain_end / on_chain_stream / metadata 不下发
    """
    name = raw.get("event")
    data = raw.get("data") or {}

    if name == "on_chat_model_stream":
        chunk = data.get("chunk")
        content = getattr(chunk, "content", None)
        # 兼容两种 AIMessageChunk.content 形态:
        #   - str: 直接当 token 发
        #   - list[dict]:OpenAI 工具调用增量格式,只把 type=='text' 的段拼成 token
        if isinstance(content, str) and content:
            return {"event": "token", "data": {"content": content}}
        if isinstance(content, list) and content:
            text = "".join(
                seg.get("text", "")
                for seg in content
                if isinstance(seg, dict) and seg.get("type") == "text"
            )
            if text:
                return {"event": "token", "data": {"content": text}}
        return None

    # on_tool_start / on_tool_end:不再下发 tool_call / tool_result 事件。
    # 真正给前端用的"工具有结果了"信号,统一在 stream_chat 里通过
    # _detect_file_event 扫描 ToolMessage.content 里的 xlsx 路径,生成
    # file 事件。LLM 内部调工具的中间过程对前端用户无意义,会刷屏。
    return None


def _collect_text(event: dict[str, Any], sink: list[str]) -> None:
    """从已映射的 token 事件中收集增量文本,用于流结束后写库。"""
    if event.get("event") != "token":
        return
    content = (event.get("data") or {}).get("content")
    if isinstance(content, str) and content:
        sink.append(content)


# .xlsx 路径匹配(同时容忍 /tmp 和 /private/tmp;macOS 上 /tmp 是 symlink,
# resolved 后变 /private/tmp,LLM 写出来的绝对路径会带 /private 前缀)
_XLSX_RE = re.compile(r"((?:/private)?/tmp/swift-agent/[\w\-]+/[^\s\"']+\.xlsx)")


def _detect_file_event(output: Any, session_id: str) -> dict | None:
    """从 write_excel tool_result.output 里提取 xlsx 路径,生成 file 事件。"""
    if output is None:
        return None
    text = str(output)
    m = _XLSX_RE.search(text)
    if not m:
        return None
    xlsx_path = m.group(1)
    p = Path(xlsx_path)
    if not p.exists() or not p.is_file():
        return None
    size = p.stat().st_size
    return {
        "event": "file",
        "data": {
            # 前端调这个 url → 后端 downloads.py 走 FileResponse 返回 xlsx 流
            "url": f"/api/downloads/{session_id}/{p.name}",
            "filename": p.name,
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": size,
        },
    }