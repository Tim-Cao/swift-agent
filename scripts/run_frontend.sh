#!/usr/bin/env bash
# 启动前端开发服务
set -e

cd "$(dirname "$0")/../frontend"

if [ ! -d "node_modules" ]; then
  echo ">>> 安装依赖..."
  npm install
fi

echo ">>> 启动 vite (http://localhost:5173)"
exec npm run dev
