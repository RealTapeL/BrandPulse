#!/usr/bin/env bash
# 停止开发依赖
set -e

cd "$(dirname "$0")/.."
docker-compose -f docker-compose.dev.yml down
