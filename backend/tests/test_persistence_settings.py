"""PersistenceSettings 校验:Literal 取值 + 默认值 + env override。

测试 PersistenceSettings(PERSISTENCE_ 前缀)配置类本身的契约,
不依赖真实 checkpointer / store 实现(那些是集成测试覆盖)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import PersistenceSettings


def test_defaults():
    s = PersistenceSettings(_env_file=None)
    assert s.checkpointer_backend == "memory"
    assert s.store_backend == "memory"
    assert s.checkpoint_db_url is None
    assert s.store_db_url is None


def test_env_override(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_CHECKPOINTER_BACKEND", "postgres")
    monkeypatch.setenv("PERSISTENCE_CHECKPOINT_DB_URL", "postgresql://x/y")
    monkeypatch.setenv("PERSISTENCE_STORE_BACKEND", "postgres")
    monkeypatch.setenv("PERSISTENCE_STORE_DB_URL", "postgresql://a/b")
    s = PersistenceSettings(_env_file=None)
    assert s.checkpointer_backend == "postgres"
    assert s.store_backend == "postgres"
    assert s.checkpoint_db_url == "postgresql://x/y"
    assert s.store_db_url == "postgresql://a/b"


def test_invalid_backend_rejected():
    with pytest.raises(ValidationError):
        PersistenceSettings(checkpointer_backend="redis", _env_file=None)


def test_invalid_store_backend_rejected():
    with pytest.raises(ValidationError):
        PersistenceSettings(store_backend="redis", _env_file=None)


def test_case_insensitive_default_when_lowercase():
    """字面量大小写敏感:'MEMORY' 应当被拒绝,只接受 'memory'。"""
    with pytest.raises(ValidationError):
        PersistenceSettings(checkpointer_backend="MEMORY", _env_file=None)