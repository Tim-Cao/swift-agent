#!/bin/bash
# ============================================================================
# 多测试套件运行脚本
# ----------------------------------------------------------------------------
# 用法:
#   ./scripts/run_tests.sh                  # 跑所有 suite
#   ./scripts/run_tests.sh backend          # 只跑指定 suite
#   ./scripts/run_tests.sh backend frontend # 跑多个
#
# 添加新 suite: 编辑下方 SUITES 数组,用 "suite_name:command:output_dir" 格式
# ============================================================================

set -e

# 切换到 backend 根目录(用绝对路径,避免后面 cd 失效)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}/.."

# 用 venv 的 pytest(避免系统 Python 缺 fastapi 等依赖)
if [ -x ".venv/bin/pytest" ]; then
  PYTEST=".venv/bin/pytest"
else
  PYTEST="pytest"
fi

REPORTS_DIR="reports"
RUN_ID=$(date +%Y-%m-%d_%H-%M)
RUN_DIR="${REPORTS_DIR}/${RUN_ID}"
mkdir -p "${RUN_DIR}/report"

# ============================================================================
# ⚙️ 在这里配置你的测试套件
# ----------------------------------------------------------------------------
# 格式: "suite_name|command|output_dir"
#  - suite_name:  套件名(用于看板分组)
#  - command:     跑测试的命令(必须输出 result.json 到 output_dir)
#  - output_dir:  套件产物目录,里面需要 result.json 和 allure-results/
# ============================================================================
# ============================================================================
# 📦 测试套件配置(按模块划分)
# ============================================================================
# 格式: "suite_name|pytest 命令|输出目录"
# 每个套件必须:
#   1. 用 pytest --json-report 输出 result.json
#   2. 用 --alluredir 输出 allure-results/
#   3. 通过 -k 筛选该模块的测试文件
# ============================================================================
SUITES=(
  # chat 模块: 5 个 chat 相关测试
  "chat|${PYTEST} tests/ -k 'chat' --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/chat"

  # sessions 模块: 会话 CRUD
  "sessions|${PYTEST} tests/test_sessions_crud.py --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/sessions"

  # uploads 模块: 上传 + 附件回填
  "uploads|${PYTEST} tests/ -k 'uploads or backfill_attachments' --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/uploads"

  # trajectory 模块: 轨迹
  "trajectory|${PYTEST} tests/test_trajectory.py --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/trajectory"

  # core 模块: 中间件 + 持久化 + 沙箱
  "core|${PYTEST} tests/ -k 'middlewares or persistence_settings or sandbox' --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/core"

  # agents 模块: skills + subagents + tools
  "agents|${PYTEST} tests/ -k 'skills or subagents or tools' --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/agents"

  # excel 模块: Excel 导入导出
  "excel|${PYTEST} tests/ -k 'excel' --json-report --json-report-file=__OUT__/result.json --alluredir=__OUT__/allure-results -v|reports/__RUN__/excel"
)

# ============================================================================
# 跑测试
# ============================================================================
echo "🧪 Run ID: ${RUN_ID}"
echo ""

# 解析要跑的 suite 列表
if [ $# -gt 0 ]; then
  REQUESTED_SUITES="$@"
  echo "🎯 指定 suite: ${REQUESTED_SUITES}"
else
  REQUESTED_SUITES=$(printf '%s\n' "${SUITES[@]}" | awk -F'|' '{print $1}' | tr '\n' ' ')
fi

SUITE_DIRS=()  # 收集每个 suite 的输出目录,后面合并 allure 用

for ENTRY in "${SUITES[@]}"; do
  IFS='|' read -r NAME COMMAND OUTPUT_DIR <<< "$ENTRY"

  # 检查是否在 REQUESTED 列表里
  if ! echo " ${REQUESTED_SUITES} " | grep -q " ${NAME} "; then
    continue
  fi

  # 替换占位符
  SUITE_OUT="${OUTPUT_DIR/__RUN__/${RUN_ID}}"
  SUITE_OUT="${SUITE_OUT/\/reports\//\/}"
  SUITE_OUT="reports/${RUN_ID}/${NAME}"
  mkdir -p "${SUITE_OUT}"

  COMMAND="${COMMAND//__OUT__/${SUITE_OUT}}"

  echo "▶ [${NAME}] ${COMMAND}"
  echo ""

  # 跑测试(失败也继续,让报告生成)
  if eval "${COMMAND}"; then
    echo "  ✅ ${NAME} 全部通过"
  else
    echo "  ⚠️  ${NAME} 有失败(继续)"
  fi
  echo ""

  SUITE_DIRS+=("${SUITE_OUT}")
done

# ============================================================================
# 合并 Allure 报告
# ============================================================================
echo "📊 合并 Allure 报告..."

ALLURE_RESULTS=()
for DIR in "${SUITE_DIRS[@]}"; do
  if [ -d "${DIR}/allure-results" ]; then
    ALLURE_RESULTS+=("${DIR}/allure-results")
  fi
done

if [ ${#ALLURE_RESULTS[@]} -gt 0 ]; then
  allure generate "${ALLURE_RESULTS[@]}" \
    --clean \
    -o "${RUN_DIR}/report" || echo "  ⚠️  allure 生成失败"
  echo "  ✅ Allure 报告: ${RUN_DIR}/report"
else
  echo "  ⚠️  没有 allure-results,跳过"
fi

# ============================================================================
# 收集每个 suite 的 summary
# ============================================================================
echo ""
echo "📝 收集 summary..."

python3 - <<PYEOF
import json
from pathlib import Path
from datetime import datetime

run_id = "${RUN_ID}"
run_dir = Path("reports/${RUN_ID}")
started_at = datetime.now().isoformat()

# 读取每个 suite 的 result.json
suites = {}
for suite_dir in sorted(run_dir.iterdir()):
    if not suite_dir.is_dir():
        continue
    name = suite_dir.name
    result_file = suite_dir / "result.json"
    if not result_file.exists():
        continue
    try:
        data = json.loads(result_file.read_text())
        summary = data.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        duration = round(summary.get("duration", 0), 2)
        rate = round(passed / total * 100, 2) if total else 0
        suites[name] = {
            "total": total, "passed": passed,
            "failed": failed, "skipped": skipped,
            "duration": duration, "rate": rate,
        }
        print(f"  ✓ {name}: {passed}/{total} 通过 ({rate}%)")
    except Exception as e:
        print(f"  ✗ {name}: {e}")

# 写主 summary.json
meta = {
    "run_id": run_id,
    "started_at": started_at,
    "suites": suites,
}

# 整体统计
total_all = sum(s["total"] for s in suites.values())
passed_all = sum(s["passed"] for s in suites.values())
failed_all = sum(s["failed"] for s in suites.values())
skipped_all = sum(s["skipped"] for s in suites.values())
duration_all = sum(s["duration"] for s in suites.values())
rate_all = round(passed_all / total_all * 100, 2) if total_all else 0

meta["summary"] = {
    "total": total_all, "passed": passed_all,
    "failed": failed_all, "skipped": skipped_all,
    "duration": duration_all, "rate": rate_all,
}

run_dir.joinpath("summary.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"\n  📊 整体: {passed_all}/{total_all} 通过 ({rate_all}%)")
PYEOF

# ============================================================================
# 更新历史索引
# ============================================================================
echo ""
echo "📋 更新历史索引..."
python3 scripts/generate_index.py

# ============================================================================
# 清理老报告(保留 30 轮)
# ============================================================================
cd "${REPORTS_DIR}"
ls -t | grep -E '^[0-9]{4}-' | tail -n +31 | xargs -r rm -rf
echo "  当前保留: $(ls -d [0-9]* 2>/dev/null | wc -l | tr -d ' ') 轮"
cd "${SCRIPT_DIR}/.."

echo ""
echo "============================================================"
echo "✅ 跑完!"
echo "============================================================"
echo ""
echo "📊 Allure 报告:    reports/${RUN_ID}/report/"
echo "📋 历史列表:       reports/index.html"
echo "📡 ReportPortal:   http://localhost:8080"
echo ""
echo "查看报告:"
echo "  allure open reports/${RUN_ID}/report"
echo ""
