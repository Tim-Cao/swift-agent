"""工具:解压 zip 到目标目录,防 zip slip 路径穿越。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from langchain_core.tools import tool

from tools import register_tool


@tool
def unzip_archive(zip_path: str, dest_dir: str) -> dict:
    """把 zip 压缩包解压到目标目录。

    参数(注意顺序,**不要反**):
      - zip_path:  **压缩包文件的绝对路径**(以 .zip 结尾)
      - dest_dir:  **解压到的目标目录绝对路径**(会自动 mkdir)

    后端 uploads API 已经把 zip 解压到 /tmp/swift-agent/<sid>/csv/,
    IntakeAgent 通常不需要再调本工具——除非用户提供的是裸 .zip 路径。
    本工具自动防 zip slip:任何含 `..` 或跳出 dest_dir 的条目会被跳过。
    仅 .csv / .CSV 文件列在 csv_files;其它文件保留但不出现在返回里。

    Returns:
        {
          "dest_dir": str,        # 解压后的目录(resolve 后)
          "csv_files": [str],     # 所有 .csv 相对路径(已排序)
          "total_count": int,     # csv 文件数
          "skipped_unsafe": [str] # 跳过的路径穿越文件名
        }

    出错时返回 {"error": "..."}。
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