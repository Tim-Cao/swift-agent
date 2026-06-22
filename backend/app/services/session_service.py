"""会话业务逻辑:新建默认名、首条消息重命名。

v6 修复(rename_if_first_user_message):
  - 调用顺序是"先 append user message,再 rename_if_first",
    所以判定从 count==0 改为 count==1(append 之后调,首条 = count==1)。
  - 增加 session.title == DEFAULT_TITLE 守卫,避免覆盖用户手动
    rename 过的会话。
  - MAX_TITLE_LEN 30 → 16,截断后补 "…" 收尾,中英文友好,
    适合左侧 260px 侧栏单行展示。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo

DEFAULT_TITLE = "新会话"
MAX_TITLE_LEN = 16  # 16 字符 + "…" ≈ 17 显示宽度,中英文都友好
TITLE_SUFFIX = "…"


async def create_default_session(db: AsyncSession, agent_name: str | None = None):
    return await repo.create_session(db, title=DEFAULT_TITLE, agent_name=agent_name)


async def rename_if_first_user_message(
    db: AsyncSession, session_id: str, content: str
) -> None:
    """新会话首次发消息后,把标题改成消息前 N 字。

    触发条件(全部满足才重命名):
      1. 该会话 user message 物理计数 == 1
         (append 之后调用,首条 = count==1;第二条起 count>=2 直接 return)
      2. 当前标题仍是默认 "新会话"(避免覆盖用户手动 rename 过的会话)

    中文按字符数截断(`len()` 是字符数,不会切到半个字);超过 MAX_TITLE_LEN
    加 "…" 后缀;首尾空白与换行清理。
    """
    count = await repo.count_user_messages(db, session_id)
    if count != 1:
        return

    session = await repo.get_session(db, session_id)
    if session is None or session.title != DEFAULT_TITLE:
        return

    title = content.strip().replace("\n", " ").replace("\r", " ")
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN].rstrip() + TITLE_SUFFIX

    if title and title != DEFAULT_TITLE:
        await repo.rename_session(db, session_id, title)