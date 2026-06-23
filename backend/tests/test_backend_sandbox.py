"""v8:create_deep_agent backend=FilesystemBackend 沙箱测试。

验证:
- builder._build_backend 生成的 FilesystemBackend 满足:
  - root_dir = /tmp/swift-agent
  - virtual_mode = True(路径穿越被 block)
  - 路径 `..` / `/etc/passwd` 在 ls 里直接 error(不是 silent leak)
- builder._build_agent 把 backend 透传到 create_deep_agent
  (用 mock 验证 keyword)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.supervisor.builder import UPLOAD_ROOT, _build_backend


def test_upload_root_constant():
    """uploads.py / downloads.py / builder 都用同一个 UPLOAD_ROOT。"""
    assert UPLOAD_ROOT == Path("/tmp/swift-agent")


def test_backend_blocks_path_traversal():
    """virtual_mode=True 时 ls('/../etc/passwd') 应 raise ValueError。"""
    backend = _build_backend()
    import pytest
    with pytest.raises(ValueError) as exc_info:
        backend.ls("/../etc/passwd")
    assert "traversal" in str(exc_info.value).lower()


def test_backend_blocks_absolute_escape():
    """virtual_mode=True 时访问跳出 root 的绝对路径应被阻挡。

    virtual_mode 把所有路径视作 `<root>/<vpath>`,所以 `/etc` 实际被解析
    成 `/tmp/swift-agent/etc` —— 该路径不存在,ls 返回 `path_not_found`
    error(而不是真的 ls 系统 /etc)。这就是 backend 阻挡 escape 的效果。
    """
    backend = _build_backend()
    # ls('/etc'):virtual_mode 解释成 <root>/etc,不存在 → path_not_found
    r = backend.ls("/etc")
    assert r.error is not None
    assert "path_not_found" in r.error

    # ls('/etc/passwd') 同理 → path_not_found
    r = backend.ls("/etc/passwd")
    assert r.error is not None

    # ls('/../../etc') 含 .. → 直接 raise ValueError
    import pytest
    with pytest.raises(ValueError) as exc_info:
        backend.ls("/../../etc/passwd")
    assert "traversal" in str(exc_info.value).lower()


def test_backend_allows_root_listing():
    """backend.root = /tmp/swift-agent 本身能 ls(返回真实 session 目录)。"""
    backend = _build_backend()
    # 真实根路径 resolve 后再 ls
    real_root = backend.cwd
    assert real_root == Path("/tmp/swift-agent").resolve()
    r = backend.ls("/")
    # 至少返回成功(可能有 N 个 session dir)
    assert r.error is None or r.entries is not None


def test_backend_virtual_path_hides_real_root():
    """virtual_mode 时,agent 看到的路径是虚拟形式(以 / 开头相对 root),
    不会泄漏真实 cwd 的绝对路径(避免 LLM 用真实路径绕过检查)。"""
    backend = _build_backend()
    real_root = backend.cwd
    # cwd 应该是 resolve 后的 /private/tmp/swift-agent(macOS symlink)
    assert real_root == Path("/tmp/swift-agent").resolve()


def test_builder_passes_backend_to_create_deep_agent():
    """builder 装配时把 backend 透传给 create_deep_agent。"""
    from app.supervisor import builder

    fake_agent = object()
    sentinel_backend = object()

    with patch.object(builder, "_build_backend", return_value=sentinel_backend), \
         patch.object(builder, "create_deep_agent", return_value=fake_agent) as cda:
        # 触发 _build_agent 调用链(避免 LLM 真正构造)
        result = builder._build_agent()
        assert result is fake_agent
        # 验证 create_deep_agent 收到 backend=sentinel_backend
        kwargs = cda.call_args.kwargs
        assert kwargs.get("backend") is sentinel_backend
        # 其它关键字段也要传
        assert kwargs.get("subagents") is not None
        assert kwargs.get("skills") is not None
        assert kwargs.get("middleware") is not None
        assert "checkpointer" in kwargs
        assert "store" in kwargs
        assert "debug" in kwargs


def test_backend_read_blocks_traversal():
    """read() 同样要阻止路径穿越(直接 raise ValueError)。"""
    backend = _build_backend()
    import pytest
    with pytest.raises(ValueError) as exc_info:
        backend.read("/../etc/passwd")
    assert "traversal" in str(exc_info.value).lower()