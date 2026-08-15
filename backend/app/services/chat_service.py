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

v9 改动:
  - 接入 SessionLogWriter:每个会话一份 JSONL(``data/sessions/<sid>/session.jsonl``),
    记录 turn_start / user_message / assistant_chunk / assistant_message /
    tool_call / tool_result / file_emitted / turn_end / session_end。
  - ``on_tool_start`` / ``on_tool_end`` 不再完全静默 —— 写日志(前端 SSE 契约不变,
    仍只发 token / file / done / error)。
  - ``on_chat_model_start`` / ``on_chat_model_end`` 用于 step 边界 + assistant_message
    收尾(含 token_usage)。
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import repository as repo
from app.services.session_service import (
    create_default_session,
    rename_if_first_user_message,
)
from app.supervisor.builder import get_supervisor, make_thread_config
from app.trajectory import SessionLogWriter

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


def _extract_stream_text(content: Any) -> str:
    """从 ``AIMessageChunk.content`` 抽出可下发的 text 增量。

    兼容两种形态:
      - str: 直接返回
      - list[dict]:只把 type=='text' 的段拼起来
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            seg.get("text", "")
            for seg in content
            if isinstance(seg, dict) and seg.get("type") == "text"
        )
    return ""


def _extract_tool_output_str(output: Any) -> str:
    """把 tool output 归一为字符串。

    ToolMessage.content 通常是 str 或 list[dict];兜底走 str。
    """
    if output is None:
        return ""
    content = getattr(output, "content", None)
    if content is not None:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                seg.get("text", "") if isinstance(seg, dict) else str(seg)
                for seg in content
            )
    # 兜底
    return str(output)


async def stream_chat(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    upload_dir: str | None = None,
    enable_web_search: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """流式生成前端 SSE 契约事件(后由 chat.py 渲染为 SSE 行)。

    事件 schema:
      - {"event": "token",      "data": {"content": "<incr>"}}
      - {"event": "tool_call",  "data": {"name": "...", "input": {...}}}
      - {"event": "tool_result","data": {"name": "...", "output": "..."}}
      - {"event": "file",       "data": {"url": "...", "filename": "...", "mime": "..."}}
      - {"event": "done",       "data": {"session_id": "..."}}
      - {"event": "error",      "data": {"message": "..."}}

    同步落盘 ``data/sessions/<session_id>/session.jsonl`` 用于回放 / 轨迹。

    upload_dir: 若前端附带(/api/uploads 返回的 upload_dir),会作为
      [UPLOAD_DIR:...] 前缀加到 message 里,让 supervisor 识别为 Excel 流水线。
    enable_web_search: 联网搜索开关,True 时 MCP 工具对 LLM 可见,False 时
      由 WebSearchGateMiddleware 在 awrap_model_call 里剔除。
    """
    # 0. 若有 upload_dir,加 [UPLOAD_DIR:...] 前缀
    llm_message = user_message
    if upload_dir and "[UPLOAD_DIR:" not in user_message:
        llm_message = f"[UPLOAD_DIR:{upload_dir}] {user_message}"

    # 1. 业务库持久化用户消息 + 触发重命名(用原始 user_message,不带前缀)
    await repo.append_message(db, session_id=session_id, role="user", content=user_message)
    await rename_if_first_user_message(db, session_id, user_message)
    await db.commit()

    # 2. 初始化 session log writer + 写 turn_start / user_message
    settings = get_settings()
    log_writer = SessionLogWriter(
        session_id=session_id,
        root=settings.trajectory_log_dir,
    )
    step_index = -1  # 首次 ``on_chat_model_start`` 时 +1 → 0
    stream_error: dict[str, Any] | None = None
    try:
        await log_writer.open(agent_name=None, model=settings.llm.model)
        # 多轮对话:从已有 JSONL 算出下一个 turn 号(同 session 内累计)
        turn_index = await log_writer.next_turn_index()
        # 参考 deepseek-harness 的 request/header 设计:
        # 只在会话 *首次* 创建时写一条 system_prompt(initial),后续每轮不再
        # 重复写同一份 prompt —— 轨迹视图把这条钉在 timeline 顶部即可。
        # (若未来 supervisor prompt 变可配 / 动态切换,这里再加 change 路径)
        if log_writer.was_empty_on_open:
            await log_writer.append(
                "system_prompt",
                {
                    "content": settings.supervisor_system_prompt,
                    "reason": "initial",
                },
            )
        await log_writer.append(
            "turn_start",
            {"turn": turn_index},
        )
        await log_writer.append(
            "user_message",
            {"content": user_message},
        )

        # 3. 调用 supervisor:input 只传本轮增量 user message。
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
            # v8.15:把 web_search_enabled 透传到 configurable,
            # WebSearchGateMiddleware 在 awrap_model_call 里读这个 flag。
            stream_config = {
                **config,
                "recursion_limit": 50,
                "configurable": {
                    **config.get("configurable", {}),
                    "web_search_enabled": enable_web_search,
                },
            }
            async for raw in agent.astream_events(
                delta_input,
                config=stream_config,
                version="v2",
            ):
                # ---- v9:写 session log(旁路,不改变 SSE 契约) ----
                await _log_raw_event(log_writer, raw, turn_index, step_index)

                # ---- 旧逻辑:映射 SSE 契约事件 ----
                raw_name = raw.get("event")
                if raw_name == "on_chat_model_start":
                    # step 边界:进入一次新的 LLM 调用
                    step_index += 1
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
                        # v9:同步落 session log
                        await log_writer.append(
                            "file_emitted",
                            {
                                "turn": turn_index,
                                "url": file_evt["data"].get("url"),
                                "filename": file_evt["data"].get("filename"),
                                "mime": file_evt["data"].get("mime"),
                                "size_bytes": file_evt["data"].get("size_bytes"),
                            },
                        )
                yield mapped
        except Exception as e:  # noqa: BLE001
            classified = _classify_stream_error(e)
            stream_error = classified
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
                await log_writer.append(
                    "file_emitted",
                    {
                        "turn": turn_index,
                        "url": file_evt["data"].get("url"),
                        "filename": file_evt["data"].get("filename"),
                        "mime": file_evt["data"].get("mime"),
                        "size_bytes": file_evt["data"].get("size_bytes"),
                    },
                )

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

        # 4. v9:收尾 — 写 turn_end(session_end 不再写,见下方注释)
        if stream_error is not None:
            turn_reason = "error"
        else:
            turn_reason = "normal"
        await log_writer.append(
            "turn_end",
            {"turn": turn_index, "reason": turn_reason},
        )
        # 注:之前每轮都写一条 ``session_end`` 是冗余且语义错误(会话生命周期
        # 不该随每条 user 消息结束)。轨迹视图只看 turns;``session_end`` 已废弃,
        # 留在 schema 中仅为兼容老日志。Reader 会忽略它。
        yield {"event": "done", "data": {"session_id": session_id}}
    except asyncio.CancelledError:
        # 客户端断连:也写 turn_end(reason=aborted),保证日志完整
        try:
            await log_writer.append(
                "turn_end",
                {"turn": turn_index, "reason": "aborted"},
            )
        except Exception:  # noqa: BLE001
            logger.debug("write aborted-end events failed", exc_info=True)
        raise
    finally:
        try:
            await log_writer.close()
        except Exception:  # noqa: BLE001
            logger.debug("close log_writer failed", exc_info=True)


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

    v9 调整:tool_call / tool_result 的细节交给 ``_log_raw_event`` 写 session log,
    本函数仍只产出 SSE 契约事件(契约不变)。
    """
    name = raw.get("event")
    data = raw.get("data") or {}

    if name == "on_chat_model_stream":
        chunk = data.get("chunk")
        content = getattr(chunk, "content", None)
        text = _extract_stream_text(content)
        if text:
            return {"event": "token", "data": {"content": text}}
        return None

    # on_tool_start / on_tool_end:不再下发 tool_call / tool_result 事件。
    # 真正给前端用的"工具有结果了"信号,统一在 stream_chat 里通过
    # _detect_file_event 扫描 ToolMessage.content 里的 xlsx 路径,生成
    # file 事件。LLM 内部调工具的中间过程对前端用户无意义,会刷屏。
    return None


async def _log_raw_event(
    writer: SessionLogWriter,
    raw: dict[str, Any],
    turn: int,
    step: int,
) -> None:
    """把 astream 原生事件落进 session log(不影响 SSE 契约)。

    处理的事件:
      - on_chat_model_stream  → assistant_chunk(delta)
      - on_chat_model_end     → assistant_message(content + usage)
      - on_tool_start         → tool_call
      - on_tool_end           → tool_result
    """
    name = raw.get("event")
    data = raw.get("data") or {}

    if name == "on_chat_model_stream":
        chunk = data.get("chunk")
        content = getattr(chunk, "content", None)
        delta = _extract_stream_text(content)
        if delta:
            await writer.append(
                "assistant_chunk",
                {"turn": turn, "step": step, "delta": delta},
            )

    elif name == "on_chat_model_end":
        # output 是 AIMessage(含完整 content + usage + response_metadata)
        output = data.get("output")
        if output is None:
            return
        content = getattr(output, "content", "") or ""
        if hasattr(content, "__iter__") and not isinstance(content, str):
            content = _extract_stream_text(content)
        usage = getattr(output, "usage_metadata", None) or {}
        # LangChain 的 usage_metadata 字段是 input_tokens / output_tokens /
        # total_tokens(input 用过就变成 cached/...)
        input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
        await writer.append(
            "assistant_message",
            {
                "turn": turn,
                "step": step,
                "content": str(content),
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            },
        )

    elif name == "on_tool_start":
        run_id = (
            data.get("run_id")
            or data.get("id")
            or (data.get("tool_run_id"))
            or ""
        )
        tool_input = data.get("input")
        # tool input 可能是 dict,LangGraph v2 也可能包成其它结构;统一转 dict
        if not isinstance(tool_input, dict):
            tool_input = {"value": tool_input} if tool_input is not None else {}
        await writer.append(
            "tool_call",
            {
                "turn": turn,
                "step": step,
                "call_id": str(run_id),
                "name": str(data.get("name", "")),
                "input": tool_input,
            },
        )

    elif name == "on_tool_end":
        run_id = (
            data.get("run_id")
            or data.get("id")
            or (data.get("tool_run_id"))
            or ""
        )
        output = data.get("output")
        output_str = _extract_tool_output_str(output)
        # LangChain 的 error 信息可能挂在 output 上,也可能挂在 data['error']
        is_error = bool(data.get("error"))
        await writer.append(
            "tool_result",
            {
                "turn": turn,
                "step": step,
                "call_id": str(run_id),
                "name": str(data.get("name", "")),
                "output": output_str,
                "is_error": is_error,
            },
        )


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