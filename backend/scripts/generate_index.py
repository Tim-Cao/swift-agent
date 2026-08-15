"""生成测试报告历史索引

输出:
  - reports/history.json     → 历史 RUN + suite 聚合数据
  - reports/index.html       → 浏览器查看
  - reports/latest/*.json    → 最新 RUN 的单值快照(各 suite 通过率)
  - reports/<run_id>/summary.json → 单次跑批的元数据
"""
import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from jinja2 import Template
except ImportError:
    print("⚠️  缺 jinja2,跑: pip install jinja2")
    sys.exit(1)


# ============================================================================
# 模板
# ============================================================================

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>测试报告归档</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7fa;
      margin: 0;
      padding: 24px;
      color: #1e293b;
    }
    h1 { margin: 0 0 4px 0; font-size: 28px; }
    .subtitle { color: #64748b; margin-bottom: 24px; font-size: 14px; }
    .summary-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }
    .summary-card {
      background: white;
      padding: 16px 20px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .summary-card .label { color: #64748b; font-size: 13px; }
    .summary-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
    .summary-card .value.green { color: #16a34a; }
    .summary-card .value.red { color: #dc2626; }
    .summary-card .value.amber { color: #d97706; }
    .filter-bar {
      background: white;
      padding: 12px 16px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: center;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .filter-bar label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-size: 14px;
    }
    .card {
      background: white;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      overflow: hidden;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 12px 16px;
      text-align: left;
      border-bottom: 1px solid #f1f5f9;
      font-size: 14px;
    }
    th {
      background: #f8fafc;
      font-weight: 600;
      color: #475569;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover { background: #f8fafc; }
    tr.row-latest { background: #eff6ff; }
    tr.row-latest:hover { background: #dbeafe; }
    .rate {
      display: inline-block;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 4px;
      min-width: 60px;
      text-align: center;
    }
    .green { color: #16a34a; background: #dcfce7; }
    .amber { color: #d97706; background: #fef3c7; }
    .red   { color: #dc2626; background: #fee2e2; }
    code {
      background: #f1f5f9;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 12px;
      color: #475569;
    }
    .btn {
      display: inline-block;
      background: #2563eb;
      color: white !important;
      text-decoration: none;
      padding: 6px 12px;
      border-radius: 4px;
      font-size: 13px;
      transition: background 0.15s;
    }
    .btn:hover { background: #1d4ed8; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      background: #e2e8f0;
      color: #475569;
      border-radius: 12px;
      font-size: 11px;
      margin-left: 4px;
    }
    .empty {
      text-align: center;
      padding: 40px;
      color: #94a3b8;
    }
  </style>
</head>
<body>
  <h1>📊 测试报告归档</h1>
  <div class="subtitle">
    共 {{ runs|length }} 轮跑批 · 套件:{{ suites|join(', ') }} · 最近 {{ runs[0].run_id if runs else 'N/A' }}
  </div>

  {% if runs %}
  <div class="summary-bar">
    <div class="summary-card">
      <div class="label">最新通过率</div>
      <div class="value {{ runs[0].color }}">{{ runs[0].summary.rate }}%</div>
    </div>
    <div class="summary-card">
      <div class="label">最近 7 天平均</div>
      <div class="value {{ avg_recent.color }}">{{ avg_recent.rate }}%</div>
    </div>
    <div class="summary-card">
      <div class="label">最近跑批</div>
      <div class="value" style="font-size:18px">{{ runs[0].run_id }}</div>
    </div>
    <div class="summary-card">
      <div class="label">累计测试用例</div>
      <div class="value">{{ total_tests }}</div>
    </div>
  </div>

  <div class="filter-bar">
    <strong>筛选套件:</strong>
    {% for s in suites %}
    <label>
      <input type="checkbox" class="suite-filter" value="{{ s }}" checked>
      {{ s }}
    </label>
    {% endfor %}
    <span style="margin-left:auto">
      <input type="search" id="search" placeholder="🔍 搜索 Run ID..." style="padding:6px 10px;border:1px solid #e2e8f0;border-radius:4px">
    </span>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Run ID</th>
          <th>时间</th>
          <th>总数</th>
          {% for s in suites %}
          <th class="suite-col" data-suite="{{ s }}">{{ s }} 通过率</th>
          {% endfor %}
          <th>整体通过率</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for run in runs %}
        <tr {% if loop.first %}class="row-latest"{% endif %}>
          <td><code>{{ run.run_id }}</code></td>
          <td>{{ run.started_at[:19] }}</td>
          <td>{{ run.summary.total }}</td>
          {% for s in suites %}
          <td class="suite-cell" data-suite="{{ s }}">
            {% if run.suites.get(s) %}
            <span class="rate {{ run.suites[s].color }}">{{ run.suites[s].rate }}%</span>
            <span style="color:#94a3b8;font-size:12px">({{ run.suites[s].passed }}/{{ run.suites[s].total }})</span>
            {% else %}-{% endif %}
          </td>
          {% endfor %}
          <td>
            <span class="rate {{ run.color }}">{{ run.summary.rate }}%</span>
          </td>
          <td>
            <a class="btn" href="./{{ run.run_id }}/report/" target="_blank">📊 Allure</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="card">
    <div class="empty">还没有跑批记录。运行 <code>./scripts/run_tests.sh</code> 开始第一次。</div>
  </div>
  {% endif %}

  <script>
    // 套件筛选
    document.querySelectorAll('.suite-filter').forEach(cb => {
      cb.addEventListener('change', () => {
        const suite = cb.value;
        const visible = cb.checked;
        document.querySelectorAll(`[data-suite="${suite}"]`).forEach(el => {
          el.style.display = visible ? '' : 'none';
        });
      });
    });

    // 搜索
    document.getElementById('search').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      document.querySelectorAll('tbody tr').forEach(tr => {
        const id = tr.querySelector('code').textContent.toLowerCase();
        tr.style.display = id.includes(q) ? '' : 'none';
      });
    });
  </script>
</body>
</html>
"""


# ============================================================================
# 工具函数
# ============================================================================

def color_for(rate):
    if rate >= 95: return "green"
    if rate >= 80: return "amber"
    return "red"


def collect_history(reports_dir: Path) -> list:
    """收集所有 run 的 summary"""
    runs = []
    if not reports_dir.exists():
        return runs

    for run_dir in sorted(reports_dir.glob("20*"), reverse=True):
        if not run_dir.is_dir():
            continue
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        try:
            meta = json.loads(summary_path.read_text())
        except Exception:
            continue

        if "summary" not in meta:
            continue

        rate = meta["summary"]["rate"]
        meta["color"] = color_for(rate)
        # 给每个 suite 也加上 color
        for suite_name, suite_data in meta.get("suites", {}).items():
            suite_data["color"] = color_for(suite_data["rate"])
        runs.append(meta)

    return runs


def collect_all_suite_names(runs: list) -> list:
    """收齐所有 suite 名(保持稳定顺序)"""
    names = []
    for run in runs:
        for name in run.get("suites", {}).keys():
            if name not in names:
                names.append(name)
    return sorted(names)


def compute_avg(runs: list, n: int = 7) -> dict:
    """最近 N 轮平均通过率"""
    if not runs:
        return {"rate": 0, "color": "red"}
    recent = runs[:n]
    total = sum(r["summary"]["total"] for r in recent)
    passed = sum(r["summary"]["passed"] for r in recent)
    rate = round(passed / total * 100, 2) if total else 0
    return {"rate": rate, "color": color_for(rate)}


# ============================================================================
# 主入口
# ============================================================================

def main():
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    # 1. 收集历史
    runs = collect_history(reports_dir)
    suites = collect_all_suite_names(runs)
    avg_recent = compute_avg(runs, n=7)
    total_tests = sum(r["summary"]["total"] for r in runs)

    # 2. 写 history.json(所有 RUN 的聚合,扁平结构方便外部消费)
    history_path = reports_dir / "history.json"
    flat_history = []
    for run in runs:
        flat = {
            # rate 字段放最前面(stat panel 直接取)
            "summary_rate": run["summary"]["rate"],
            "summary_passed": run["summary"]["passed"],
            "summary_total": run["summary"]["total"],
            "summary_failed": run["summary"]["failed"],
            "summary_skipped": run["summary"]["skipped"],
        }
        # 套件字段
        for suite_name, suite_data in run.get("suites", {}).items():
            flat[f"suite_{suite_name}_rate"] = suite_data["rate"]
            flat[f"suite_{suite_name}_passed"] = suite_data["passed"]
            flat[f"suite_{suite_name}_total"] = suite_data["total"]
        # 元数据
        flat["run_id"] = run["run_id"]
        flat["started_at"] = run["started_at"]
        flat["color"] = run["color"]
        # 预拼接好的 Allure 详情链接(让 table 直接渲染成可点击列)
        flat["details_url"] = f"/{run['run_id']}/report/"
        flat_history.append(flat)

    history_path.write_text(
        json.dumps(flat_history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2.5 给 ReportPortal / 外部消费者准备 runs_var.json(数组 [{text, value}] 格式)
    runs_var = [
        {
            "text": f"{r['run_id']}  ({r['started_at'][:19]})",
            "value": r["run_id"],
        }
        for r in runs
    ]
    (reports_dir / "runs_var.json").write_text(
        json.dumps(runs_var, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3. 生成 latest/*.json(最新 RUN 的快照,供外部 dashboard 拉取)
    latest_dir = reports_dir / "latest"
    latest_dir.mkdir(exist_ok=True)

    if runs:
        latest = runs[0]  # 最新一轮

        # 元数据
        for key, val in [("run_id", latest["run_id"]),
                          ("started_at", latest["started_at"][:19])]:
            (latest_dir / f"{key}_value.json").write_text(
                json.dumps({"value": val}, ensure_ascii=False),
                encoding="utf-8",
            )
            (latest_dir / f"{key}_var.json").write_text(
                json.dumps([{"text": val, "value": val}], ensure_ascii=False),
                encoding="utf-8",
            )

        # 整体
        (latest_dir / "overall.json").write_text(
            json.dumps({"value": latest["summary"]["rate"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        # 每个 suite
        for suite_name in suites:
            suite_data = latest.get("suites", {}).get(suite_name, {})
            rate = suite_data.get("rate", 0)
            (latest_dir / f"{suite_name}.json").write_text(
                json.dumps({"value": rate}, ensure_ascii=False),
                encoding="utf-8",
            )

        print(f"   · latest/*.json: {1 + len(suites)} 个单值文件")

    # 4. 每个 run 目录里也写一份同样的单值文件(让 dashboard 选任意 RUN 时能拿)
    #   结构:reports/<run_id>/{overall, <suite>, run_id, started_at}.json
    for run in runs:
        run_dir = reports_dir / run["run_id"]
        run_dir.mkdir(exist_ok=True)
        # 整体
        (run_dir / "overall.json").write_text(
            json.dumps({"value": run["summary"]["rate"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        # 每个 suite
        for suite_name in suites:
            suite_data = run.get("suites", {}).get(suite_name, {})
            (run_dir / f"{suite_name}.json").write_text(
                json.dumps({"value": suite_data.get("rate", 0)}, ensure_ascii=False),
                encoding="utf-8",
            )
        # 元数据(给当前 RUN 标识用)
        (run_dir / "run_id.json").write_text(
            json.dumps({"value": run["run_id"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (run_dir / "started_at.json").write_text(
            json.dumps({"value": run["started_at"][:19]}, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"   · 每个 run 目录: {1 + len(suites) + 2} 个单值文件 × {len(runs)} 轮")

    # 4. 生成 index.html
    html = Template(INDEX_TEMPLATE).render(
        runs=runs,
        suites=suites,
        avg_recent=avg_recent,
        total_tests=total_tests,
    )
    index_path = reports_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")

    print(f"✅ 索引生成: {index_path}")
    print(f"   · history.json: {len(runs)} 轮")
    print(f"   · 套件: {', '.join(suites) if suites else '(无)'}")
    print(f"   · 最新: {runs[0]['run_id'] if runs else 'N/A'}")


if __name__ == "__main__":
    main()
