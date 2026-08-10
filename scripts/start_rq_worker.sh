#!/usr/bin/env bash
# 启动 RQ worker，同时消费采集和 Agent 后台任务队列。
# --with-scheduler 负责把采集失败后的延迟重试任务从 ScheduledJobRegistry 取回队列。
# 用法：scripts/start_rq_worker.sh
# 前置：Redis 已启动（本地 redis-server --daemonize yes）
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate || true
export PYTHONPATH="$(pwd)/src/backend:$(pwd)/src:${PYTHONPATH:-}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"

exec rq worker brandpulse-crawl brandpulse-agent brandpulse-ml brandpulse-report \
  --path "$(pwd)/src/backend" \
  --url "$REDIS_URL" \
  --with-scheduler
