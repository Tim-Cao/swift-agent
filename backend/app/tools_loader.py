"""上传工具的加载器。

用户上传的 zip 包解压到 ``backend/data/uploaded_tools/<tool_id>/``,
其中的 .py 模块被 import,模块里调用 ``register_tool(...)`` 注册的工具
被捕获进 TOOLKIT / TOOL_META。

安全说明:import 会执行任意代码 —— 这是「用户自带工具」的固有语义,
仅适用于本地自用场景,不要暴露到公网。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from tools import TOOLKIT, TOOL_META, ToolMeta, register_tool

logger = logging.getLogger(__name__)

# 上传工具的解压根目录(相对 backend/)
UPLOADED_ROOT = Path("data/uploaded_tools")

# zip 大小上限 50MB
MAX_ZIP_BYTES = 50 * 1024 * 1024

# zip 内允许的文件后缀
ALLOWED_SUFFIXES = {".py", ".json", ".md", ".txt", ".csv"}


class ToolLoadError(Exception):
    """工具包加载失败(对外转成 400 提示)。"""


def _safe_extract(zip_path: Path, dest: Path) -> list[str]:
    """解压 zip 到 dest,防 zip slip 路径穿越。返回解出的 .py 相对路径列表。"""
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    py_files: list[str] = []

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = (dest / member.filename).resolve()
            # 防 zip slip:目标必须仍在 dest 之下
            if not str(target).startswith(str(dest_resolved) + "/"):
                raise ToolLoadError(f"非法路径(疑似路径穿越): {member.filename}")
            suffix = Path(member.filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                # 其它后缀直接跳过(不报错),只允许白名单类型落盘
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if suffix == ".py":
                py_files.append(member.filename)

    if not py_files:
        raise ToolLoadError("zip 包里没有 .py 文件(工具模块)")
    return sorted(py_files)


def _read_manifest(dest: Path) -> dict[str, Any]:
    """读取可选的 manifest.json(显示名 / 描述)。"""
    manifest_path = dest / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("[tools] manifest.json 解析失败,忽略: %s", e)
        return {}


def load_tool_package(
    tool_id: str,
    zip_path: Path,
    *,
    known_names: set[str] | None = None,
) -> list[ToolMeta]:
    """加载一个上传的工具包,返回它注册的工具元数据列表。

    步骤:解压 → 逐个 import .py → 收集新注册的工具 → 清理 import 缓存。

    known_names:已经被注册过的工具名(「替换实现」时传旧工具名)。
      本包注册的名字若在 known_names 里,也算本包的工具 ——
      否则替换时因为"名字早就在 TOOLKIT 里"会被误判成"没注册任何工具"。
    """
    dest = UPLOADED_ROOT / tool_id
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    py_files = _safe_extract(zip_path, dest)
    manifest = _read_manifest(dest)

    # import 前记下当前已注册的工具名,用于识别「本包新注册了哪些」
    before = set(TOOLKIT.keys())

    loaded_modules: list[str] = []
    try:
        for rel in py_files:
            src_path = dest / rel
            module_name = f"uploaded_tools.{tool_id}.{Path(rel).stem}"
            # 保证父包存在
            parent = module_name.rsplit(".", 1)[0]
            if parent not in sys.modules:
                pkg_init = UPLOADED_ROOT / tool_id / "__init__.py"
                pkg_init.parent.mkdir(parents=True, exist_ok=True)
                if not pkg_init.exists():
                    pkg_init.write_text("", encoding="utf-8")
                spec = importlib.util.spec_from_file_location(
                    parent, pkg_init, submodule_search_locations=[str(pkg_init.parent)]
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[parent] = mod
                    spec.loader.exec_module(mod)

            spec = importlib.util.spec_from_file_location(module_name, src_path)
            if spec is None or spec.loader is None:
                raise ToolLoadError(f"无法加载模块: {rel}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            loaded_modules.append(module_name)
    except ToolLoadError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ToolLoadError(f"工具模块执行失败: {e}") from e
    finally:
        # 清理 import 缓存,避免同名模块在热重载时拿到旧代码
        for name in loaded_modules:
            sys.modules.pop(name, None)

    new_names = [n for n in TOOLKIT.keys() if n not in before]
    if known_names:
        # 替换模式:本包重新注册了旧工具名(同名覆盖),也算本包的工具
        for n in known_names:
            if n in TOOLKIT and n not in new_names:
                new_names.append(n)
    if not new_names:
        raise ToolLoadError(
            "工具包没有注册任何工具(需在 .py 里调用 register_tool(name, tool))"
        )

    # 用 manifest 里的显示名 / 描述覆盖(manifest 是可选的)
    meta_overrides: dict[str, dict[str, Any]] = {}
    if manifest:
        tools_meta = manifest.get("tools")
        if isinstance(tools_meta, dict):
            meta_overrides = tools_meta

    result: list[ToolMeta] = []
    for name in new_names:
        meta = TOOL_META.get(name)
        if meta is None:
            continue
        override = meta_overrides.get(name) or {}
        meta.source_dir = str(dest)
        meta.builtin = False
        if override.get("display_name"):
            meta.display_name = str(override["display_name"])
        elif manifest.get("display_name") and len(new_names) == 1:
            meta.display_name = str(manifest["display_name"])
        if override.get("description"):
            meta.description = str(override["description"])
        elif manifest.get("description") and len(new_names) == 1:
            meta.description = str(manifest["description"])
        result.append(meta)

    logger.info(
        "[tools] 已加载工具包 %s → %s", tool_id, ", ".join(m.name for m in result)
    )
    return result


def unload_tool_package(tool_id: str, tool_names: list[str]) -> None:
    """卸载一个工具包:注销它注册的工具并删掉解压目录。"""
    from tools import unregister_tool

    for name in tool_names:
        unregister_tool(name)
    shutil.rmtree(UPLOADED_ROOT / tool_id, ignore_errors=True)


__all__ = [
    "UPLOADED_ROOT",
    "MAX_ZIP_BYTES",
    "ToolLoadError",
    "load_tool_package",
    "unload_tool_package",
]
