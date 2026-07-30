#!/usr/bin/env bash
# 启动开发依赖（Postgres / Redis / Prometheus）
# 后端/前端默认走本地运行；如需容器化运行，请扩展 docker-compose.dev.yml。
set -e

cd "$(dirname "$0")/.."
docker-compose -f docker-compose.dev.yml up -d

echo "开发依赖已启动："
echo "  Postgres  : localhost:5432"
echo "  Redis     : localhost:6379"
echo "  Prometheus: localhost:9090"
echo ""
echo "本地运行后端/前端："
echo "  .venv/bin/python -m uvicorn brandpulse.api.app:app --host 0.0.0.0 --port 8000"
echo "  cd src/frontend && npm run dev"
