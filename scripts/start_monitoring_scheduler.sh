#!/usr/bin/env bash
# BrandPulse 独立自动采集/报告调度器。
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate || true
export PYTHONPATH="$(pwd)/src/backend:$(pwd)/src:${PYTHONPATH:-}"
exec .venv/bin/python -m brandpulse.monitoring.runner
