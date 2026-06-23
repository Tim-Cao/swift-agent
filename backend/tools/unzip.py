"""工具:解压 zip 到目标目录,防 zip slip 路径穿越。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from langchain_core.tools import tool

from tools import register_tool


@tool
def unzip_archive(zip_path: str, dest_dir: str) -> dict:
    """解压 zip 到 dest_dir,返回 {csv_files: [相对路径...], total_count: int}。

    自动防 zip slip:任何包含 `..` 或绝对路径的条目会被拒绝并跳过。
    仅提取 .csv / .CSV 文件;其它文件保留但不在返回里列出。
    """
    src = Path(zip_path)
    dst = Path(dest_dir)
    if not src.exists():
        return {"error": f"zip not found: {zip_path}"}
    if not src.is_file():
        return {"error": f"not a file: {zip_path}"}
    dst.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    skipped: list[str] = []
    with zipfile.ZipFile(src) as zf:
        for member in zf.infolist():
            # 防 zip slip:目标路径必须仍在 dest_dir 之下
            target = (dst / member.filename).resolve()
            if not str(target).startswith(str(dst.resolve())):
                skipped.append(member.filename)
                continue
            # 目录条目
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src_f, target.open("wb") as dst_f:
                dst_f.write(src_f.read())
            if member.filename.lower().endswith(".csv"):
                extracted.append(member.filename)

    return {
        "dest_dir": str(dst.resolve()),
        "csv_files": sorted(extracted),
        "total_count": len(extracted),
        "skipped_unsafe": skipped,
    }


register_tool("unzip_archive", unzip_archive)