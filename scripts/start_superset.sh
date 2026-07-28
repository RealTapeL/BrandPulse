#!/bin/bash
# 启动本机 Superset 服务（后台运行）
# 用法: bash scripts/start_superset.sh
cd "$(dirname "$0")/.."
export SUPERSET_CONFIG_PATH=/home/lsy/BrandPulse/scripts/superset_config.py

if pgrep -f ".venv-superset/bin/superset run" > /dev/null; then
    echo "Superset 已在运行: http://127.0.0.1:8088"
    exit 0
fi

nohup .venv-superset/bin/superset run -h 0.0.0.0 -p 8088 --with-threads \
    > /home/lsy/superset.log 2>&1 &
sleep 10
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/login/)
echo "Superset 状态码: $code"
echo "看板地址: http://127.0.0.1:8088/superset/dashboard/1/  (admin / admin123)"
