#!/usr/bin/env bash
# BrandPulse 独立告警调度器。
# 告警检查不再随 FastAPI 启停，避免 API 多副本重复通知。
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate || true
export PYTHONPATH="$(pwd)/src/backend:$(pwd)/src:${PYTHONPATH:-}"
exec .venv/bin/python -m brandpulse.alerts.runner
