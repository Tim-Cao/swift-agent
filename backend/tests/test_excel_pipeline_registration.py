"""v8.3:excel_pipeline 子包注册名一致性 regression test。

之前有一次 stray edit 把 __all__ 的 "unzip_archive" 改成了 "unzip",
会破坏 from tools import excel_pipeline 的公开接口。本测试锁住:
  - __all__ 严格包含 4 个标准名
  - tools.TOOLKIT 也有这 4 个键
  - 每个键对应的 tool 函数名 == 注册名
"""

from __future__ import annotations

import pytest

from tools import TOOLKIT
from tools import excel_pipeline  # noqa: F401  触发 4 个 tool 注册


EXPECTED_TOOL_NAMES = {
    "unzip_archive",
    "inspect_csv",
    "execute_pandas_code",
    "write_excel",
}


def test_excel_pipeline_all_contains_expected():
    """__all__ 必须正好是这 4 个名字,防止 stray edit。"""
    assert set(excel_pipeline.__all__) == EXPECTED_TOOL_NAMES


def test_excel_pipeline_all_names_are_registered():
    """__all__ 里的每个名字都要在 TOOLKIT 里能找到对应 tool。"""
    for name in excel_pipeline.__all__:
        assert name in TOOLKIT, f"{name!r} 在 __all__ 但没在 TOOLKIT"


def test_toolkit_has_all_four_pipeline_tools():
    """TOOLKIT 必须注册了 4 个标准 tool,缺一不可。"""
    missing = EXPECTED_TOOL_NAMES - set(TOOLKIT.keys())
    assert not missing, f"TOOLKIT 缺: {missing}"


def test_registered_tool_function_names_match_keys():
    """TOOLKIT[name] 的可调用对象,其 __name__ 应该和 key 一致(或 @tool 包装后是底层函数名)。

    @tool 装饰器会返回一个 langchain 的 StructuredTool,但底层函数应
    仍可 .name 拿到;同时调用时参数签名应正常。
    """
    for name in EXPECTED_TOOL_NAMES:
        t = TOOLKIT[name]
        # langchain StructuredTool:有 .name 属性
        assert getattr(t, "name", None) == name, f"{name} 的 .name 不匹配"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOL_NAMES))
def test_each_tool_is_invokable(name):
    """每个 tool 必须有 .invoke 方法(LangChain Tool 的统一契约)。"""
    t = TOOLKIT[name]
    assert hasattr(t, "invoke"), f"{name} 缺 .invoke"


def test_excel_pipeline_reexports_callable_functions():
    """__all__ 里的名字也必须能从 excel_pipeline 直接 import 拿到。

    这防止 "import 的模块名是单数(tools.unzip) 而 __all__ 写的是函数名
    (unzip_archive)" 这种混淆——以前如果只 import 模块不 re-export,
    `from tools.excel_pipeline import unzip_archive` 会 ImportError。

    注意:re-export 的是 LangChain 的 StructuredTool(由 @tool 装饰器包
    装),不是裸函数,callable() 会返回 False。验证方式是 .invoke 存在。
    """
    import importlib

    for name in EXPECTED_TOOL_NAMES:
        mod = importlib.import_module("tools.excel_pipeline")
        obj = getattr(mod, name, None)
        assert obj is not None, f"excel_pipeline 没 re-export {name}"
        # 必须是 LangChain Tool(有 .invoke),不是模块/类/None
        assert hasattr(obj, "invoke"), f"excel_pipeline.{name} 不是 LangChain Tool"
        assert getattr(obj, "name", None) == name, f"excel_pipeline.{name} 名字属性不匹配"
