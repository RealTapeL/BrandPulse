#!/usr/bin/env bash
# 启动 RQ worker，消费 brandpulse-crawl 队列。
# 用法：scripts/start_rq_worker.sh
# 前置：Redis 已启动（本地 redis-server --daemonize yes）
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate || true
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src/backend"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"

exec rq worker brandpulse-crawl \
  --path "$(pwd)/src/backend" \
  --url "$REDIS_URL"
