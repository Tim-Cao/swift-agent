"""工具:把 CSV 写成规范美化 Excel(加粗表头 / 斑马纹 / 自动列宽 / 冻结首行 / 数字千分位)。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from langchain_core.tools import tool
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from tools import register_tool

# 5w 行以上不开斑马纹(openpyxl 样式应用是 O(n) per cell)
ZEBRA_THRESHOLD = 50_000
HEADER_FILL = PatternFill(fill_type="solid", fgColor="D9E1F2")  # 浅蓝
ZEBRA_FILL = PatternFill(fill_type="solid", fgColor="F2F6FC")   # 极浅蓝
HEADER_FONT = Font(bold=True, color="1F4E78")
CENTER = Alignment(horizontal="center", vertical="center")


@tool
def write_excel(
    csv_path: str,
    output_path: str,
    sheet_name: str = "Result",
) -> dict:
    """把 CSV 写成规范美化 Excel。

    样式:
      - 表头加粗 + 浅蓝填充
      - 隔行斑马纹(行数 <= 5w 时)
      - 自动列宽(基于内容字符数,上限 50)
      - 冻结首行
      - 数字千分位 / 日期格式 / 居中

    Returns:
        {"output_path": str, "row_count": int, "columns": [str], "size_bytes": int}
    """
    src = Path(csv_path)
    out = Path(output_path)
    if not src.exists():
        return {"error": f"csv not found: {csv_path}"}
    out.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(src)

    # 第一步:pandas 写 xlsx(含 datetime 列处理)
    df.to_excel(out, sheet_name=sheet_name, index=False)

    # 第二步:openpyxl 加样式
    wb = load_workbook(out)
    ws = wb[sheet_name]

    # 表头样式 + 列宽
    max_col_widths: dict[int, int] = {}
    for row in ws.iter_rows(min_row=1, max_row=1):
        for cell in row:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = CENTER

    # 数据行:数字 / 日期格式 + 斑马纹
    apply_zebra = len(df) <= ZEBRA_THRESHOLD
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        for cell in row:
            val = cell.value
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cell.number_format = "#,##0.##"
            # 日期格式由 pandas 写时已经处理好,这里不重复设
            cell.alignment = Alignment(horizontal="left", vertical="center")
            if apply_zebra and row_idx % 2 == 0:
                cell.fill = ZEBRA_FILL
            # 列宽统计
            col_idx = cell.column
            text_len = len(str(val)) if val is not None else 0
            max_col_widths[col_idx] = max(max_col_widths.get(col_idx, 0), text_len)

    # 列宽(取表头与数据列宽最大值,上限 50)
    for col_idx in range(1, ws.max_column + 1):
        header_len = len(str(ws.cell(row=1, column=col_idx).value or "")) + 2
        data_len = max_col_widths.get(col_idx, 0) + 2
        width = min(max(header_len, data_len), 50)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # 冻结首行
    ws.freeze_panes = "A2"

    wb.save(out)

    return {
        "output_path": str(out.resolve()),
        "row_count": int(len(df)),
        "columns": list(df.columns),
        "size_bytes": out.stat().st_size,
    }


register_tool("write_excel", write_excel)