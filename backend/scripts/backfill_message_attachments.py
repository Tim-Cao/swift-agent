"""一次性回填脚本:扫描历史 assistant 消息,从 content 里提取 xlsx 路径
并把 {url, filename, mime, size_bytes} 写进 meta_json['attachments']。

为什么需要:
  v8.14 之前的 stream_chat 只把 file 事件通过 SSE 推给前端,没写数据库。
  那些历史 assistant 消息(以及它们的 xlsx 文件)的关联信息只活在
  流期间 —— 页面刷新/前端重启后下载按钮就消失。
  本脚本一次性回填:扫描 content,匹配 xlsx 路径,验证文件还在,
  写 meta_json(只在没 attachments 时写,幂等)。

用法:
  cd backend
  uv run python -m scripts.backfill_message_attachments
  # 默认扫描 DB_URL 指向的库(从环境变量读)

幂等:
  - meta_json 已经含 attachments 键的 → 跳过
  - meta_json 为 None 或不含 attachments → 解析 content → 写
  - 多次跑结果相同

副作用:
  - 只 update messages.meta_json;不动 content / role / 其他字段
  - 不删文件
  - 不删消息
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

# /private/tmp/swift-agent/<sid>/...xlsx 或 /tmp/swift-agent/<sid>/...xlsx
# 与 chat_service._XLSX_RE 保持一致(同一正则,避免漏匹配)
_XLSX_RE = re.compile(r"((?:/private)?/tmp/swift-agent/[\w\-]+/[^\s\"']+\.xlsx)")

XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

logger = logging.getLogger("backfill_attachments")


def extract_attachments_from_content(
    content: str | None, session_id: str
) -> list[dict[str, Any]]:
    """从 assistant 消息文本里抽取 xlsx 附件信息(文件存在时才返回)。

    复用 chat_service._detect_file_event 的核心逻辑:扫 xlsx 路径 →
    Path.exists() 验证 → 构造 attachment dict。
    """
    if not content:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _XLSX_RE.finditer(content):
        xlsx_path = m.group(1)
        if xlsx_path in seen:
            continue
        seen.add(xlsx_path)
        p = Path(xlsx_path)
        if not p.exists() or not p.is_file():
            # 文件已被清理(用户清理 /tmp、session 过期)→ 跳过,
            # 不会让用户看到"点了下载 404"
            logger.info(
                "skip: xlsx gone from disk, message content has path=%s", xlsx_path,
            )
            continue
        out.append({
            "url": f"/api/downloads/{session_id}/{p.name}",
            "filename": p.name,
            "mime": XLSX_MIME,
            "size_bytes": p.stat().st_size,
        })
    return out


async def backfill_once() -> dict[str, int]:
    """扫描所有 assistant 消息,缺 attachments 的回填;返回统计。"""
    from app.db.base import init_db
    from app.db.models import Message
    from app.db.session import session_scope

    await init_db()
    stats = {"scanned": 0, "backfilled": 0, "skipped_already_filled": 0, "no_xlsx": 0}

    async with session_scope() as db:
        # 一次性拉所有 assistant 消息
        result = await db.execute(
            select(Message).where(Message.role == "assistant").order_by(Message.created_at)
        )
        msgs = list(result.scalars())

    for m in msgs:
        stats["scanned"] += 1

        # 解析现有 meta
        meta: dict[str, Any] = {}
        if m.meta_json:
            try:
                meta = json.loads(m.meta_json)
            except json.JSONDecodeError:
                meta = {}

        # 已存在 attachments 键(不论非空)→ 视为已回填,跳过
        if "attachments" in meta:
            stats["skipped_already_filled"] += 1
            continue

        atts = extract_attachments_from_content(m.content, m.session_id)
        if not atts:
            stats["no_xlsx"] += 1
            continue

        meta["attachments"] = atts
        new_meta_json = json.dumps(meta, ensure_ascii=False)

        # update meta_json
        async with session_scope() as db:
            # 重新查一遍(老 session 已 close)
            row = await db.get(Message, m.id)
            if row is None:
                continue
            row.meta_json = new_meta_json
        stats["backfilled"] += 1
        logger.info(
            "backfilled message id=%s session=%s att_count=%d",
            m.id, m.session_id, len(atts),
        )

    return stats


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    stats = asyncio.run(backfill_once())
    logger.info("backfill done: %s", stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
