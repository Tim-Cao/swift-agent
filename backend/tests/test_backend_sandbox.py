"""v11:create_deep_agent backend=LocalShellBackend(virtual_mode=False) 测试。

v8 时用的是 ``FilesystemBackend(virtual_mode=True)``(路径被限制在 root 下,
agent 看到虚拟路径)。v11 改用 ``LocalShellBackend(virtual_mode=False)``:
agent 看到真实路径,可以自由读写工作目录 —— 真正的边界由业务代码
(uploads / downloads 的 session 归属校验)把守。

验证:
- build_backend 生成的 LocalShellBackend 满足:
  - root_dir = /tmp/swift-agent
  - virtual_mode = False
  - cwd 指向 resolve 后的真实路径
- build_agent 把 backend 透传到 create_deep_agent(用 mock 验证 keyword)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.supervisor.agent_runtime import UPLOAD_ROOT, build_agent, build_backend


def test_upload_root_constant():
    """uploads.py / downloads.py / runtime 都用同一个 UPLOAD_ROOT。"""
    assert UPLOAD_ROOT == Path("/tmp/swift-agent")


def test_backend_is_local_shell_with_real_paths():
    """v11:LocalShellBackend + virtual_mode=False(agent 看到真实路径)。"""
    backend = build_backend()
    assert type(backend).__name__ == "LocalShellBackend"
    assert backend.virtual_mode is False
    # cwd 指向 resolve 后的真实路径(macOS 上 /tmp 是 /private/tmp 的 symlink)
    assert backend.cwd == Path("/tmp/swift-agent").resolve()


def test_backend_root_is_upload_root():
    """backend 的根就是 UPLOAD_ROOT。"""
    backend = build_backend()
    assert backend.cwd == UPLOAD_ROOT.resolve()


def test_build_agent_passes_backend_to_create_deep_agent():
    """build_agent 装配时把 backend 透传到 create_deep_agent。"""
    from app.supervisor import agent_runtime

    fake_agent = object()
    sentinel_backend = object()

    with patch.object(
        agent_runtime, "build_backend", return_value=sentinel_backend
    ), patch.object(
        agent_runtime, "create_deep_agent", return_value=fake_agent
    ) as cda:
        result = build_agent(name="t", system_prompt="p")
        assert result is fake_agent
        kwargs = cda.call_args.kwargs
        assert kwargs.get("backend") is sentinel_backend
        # 其它关键字段也要传
        assert kwargs.get("system_prompt") == "p"
        assert "debug" in kwargs


def test_build_agent_passes_subagents_and_tools():
    """子 agent 和工具都要透传(create_deep_agent 的 subagents= 参数)。"""
    from app.supervisor import agent_runtime

    with patch.object(agent_runtime, "create_deep_agent") as cda:
        build_agent(
            name="t",
            system_prompt="p",
            tools=["tool-a"],
            subagents=[{"name": "child"}],
        )
        kwargs = cda.call_args.kwargs
        assert kwargs.get("tools") == ["tool-a"]
        assert kwargs.get("subagents") == [{"name": "child"}]
