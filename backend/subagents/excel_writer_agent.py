"""ExcelWriterAgent:把结果 CSV 写成规范美化 Excel。"""

from __future__ import annotations

from tools import get_tools

EXCEL_WRITER_AGENT = {
    "name": "ExcelWriterAgent",
    "description": (
        "把 DataProcessingAgent 产出的 result.csv 写成规范美化 Excel:"
        "表头加粗 / 斑马纹 / 自动列宽 / 冻结首行 / 数字千分位。"
    ),
    "system_prompt": (
        "你是 ExcelWriterAgent。流程:\n"
        "1) 拿到 DataProcessingAgent 的 result.csv 路径\n"
        "2) 调 write_excel 工具,output_path 设为:\n"
        "   <session_dir>/result.xlsx(与 result.csv 同目录)\n"
        "3) 返回 {output_path, row_count, columns, size_bytes} 给 Supervisor\n"
        "\n"
        "异常处理:\n"
        "- write_excel 返回 error 时,反馈给 Supervisor 重试\n"
        "- 不要尝试自己写 Excel,必须用工具(样式标准化)"
    ),
    "tools": get_tools(["write_excel"]),
}

__all__ = ["EXCEL_WRITER_AGENT"]