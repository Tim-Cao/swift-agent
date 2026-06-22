"""DataProcessingAgent:执行 RuleParserAgent 生成的 pandas 代码,产出结果 CSV。"""

from __future__ import annotations

from tools import get_tools

DATA_PROCESSING_AGENT = {
    "name": "DataProcessingAgent",
    "description": (
        "接收 RuleParserAgent 生成的 pandas 代码,在受控沙箱里执行,"
        "把 RESULT_DF 写出成 result.csv 并返回路径给 Supervisor。"
    ),
    "system_prompt": (
        "你是 DataProcessingAgent。流程:\n"
        "1) 拿到 RuleParserAgent 输出的代码 + IntakeAgent 给的 (csv_dir, allowed_files)\n"
        "2) 调 execute_pandas_code 工具,output_csv 设为:\n"
        "   <session_dir>/result.csv(supervisor 会告诉你 session_dir)\n"
        "3) 拿到结果后,把 {result_csv, row_count, columns, head_sample} 返回给 Supervisor\n"
        "\n"
        "异常处理:\n"
        "- execute_pandas_code 返回 {ok: false, error, traceback} 时,\n"
        "  把 error + traceback 完整反馈给 Supervisor,让它回 RuleParserAgent 重写\n"
        "- 不要自己修改代码\n"
    ),
    "tools": get_tools(["execute_pandas_code"]),
}

__all__ = ["DATA_PROCESSING_AGENT"]