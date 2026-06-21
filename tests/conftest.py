"""pytest 全局 fixture。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 强制使用内存数据库,避免污染本地 data/
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_API_KEY", "test-key")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
