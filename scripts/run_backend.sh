#!/usr/bin/env bash
# 启动后端开发服务
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo ">>> 创建虚拟环境..."
  uv sync
fi

echo ">>> 启动 uvicorn (http://localhost:8000)"
exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
