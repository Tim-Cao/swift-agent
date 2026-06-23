"""IntakeAgent:解压 zip + 解析所有 CSV 结构。"""

from __future__ import annotations

from tools import get_tools

INTAKE_AGENT = {
    "name": "IntakeAgent",
    "description": (
        "解压用户上传的 zip 压缩包,扫描所有 CSV 文件,提取字段名 / "
        "数据样例 / 编码 / 行数,产出结构化文件清单交给后续 Agent。"
        "适合:用户消息含 [UPLOAD_DIR:<path>] 标记时优先调用。"
    ),
    "system_prompt": (
        "你是 IntakeAgent。你的职责:\n"
        "1) 拿到上传目录路径后,先调 unzip_archive 解压 zip(若还未解压)\n"
        "2) 对目录里每个 CSV 调 inspect_csv 获取结构信息\n"
        "3) 把所有文件结构组装成一个清晰的 JSON 返回给 Supervisor:\n"
        "   { csv_files: [{name, columns: [...], row_count, sample: [...]}] }\n"
        "\n"
        "禁止:\n"
        "- 猜测字段含义或推断数据语义(那是 RuleParserAgent 的事)\n"
        "- 修改任何文件\n"
        "- 调任何文件写入工具\n"
    ),
    "tools": get_tools(["unzip_archive", "inspect_csv"]),
}

__all__ = ["INTAKE_AGENT"]