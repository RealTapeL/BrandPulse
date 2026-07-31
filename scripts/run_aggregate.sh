#!/usr/bin/env bash
# 运行指标聚合 job，把 brand_indicators_daily 聚合到 indicators 表。
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate || true
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src/backend"

.venv/bin/python src/backend/brandpulse/indicators/jobs/aggregate.py "$@"
