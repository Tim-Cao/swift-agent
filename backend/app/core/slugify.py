"""「提供商 ID」(slug)的规整。

前端给的是用户自己起的短标识,后端统一规整成小写 + 短横线的形式,
避免出现「同一个 ID 两种写法」导致的重名/歧义。

保留 Unicode 单词字符(``\\w`` 在 Python 3 的 str 模式下是 Unicode-aware),
所以中文 ID 也能用 —— 规整只处理空白和标点。
"""

from __future__ import annotations

import re

# 下划线先换成短横线(``\w`` 包含 ``_``,不单独处理会留在结果里)
_UNDERSCORE = re.compile(r"_")
# 连续的非单词字符压成一个短横线
_SEP = re.compile(r"[^\w\-]+", re.UNICODE)
# 多个短横线压成一个
_DASHES = re.compile(r"-{2,}")


def slugify(text: str | None) -> str:
    """把任意文本规整成 slug;全是标点时返回空串。

    >>> slugify("  MiniMax  ")
    'minimax'
    >>> slugify("openai_compatible")
    'openai-compatible'
    >>> slugify("我的提供商")
    '我的提供商'
    >>> slugify("!!!")
    ''
    """
    s = (text or "").strip().lower()
    s = _UNDERSCORE.sub("-", s)
    s = _SEP.sub("-", s)
    s = _DASHES.sub("-", s)
    return s.strip("-_")


__all__ = ["slugify"]
