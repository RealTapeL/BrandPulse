#!/bin/bash
# 启动本机 Superset 服务（后台运行，日志写入项目 logs/ 目录）
# 用法: bash scripts/start_superset.sh
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
export SUPERSET_CONFIG_PATH="$PROJECT_ROOT/scripts/superset_config.py"

if pgrep -f ".venv-superset/bin/superset run" > /dev/null; then
    echo "Superset 已在运行: http://192.168.0.109:8088"
    echo "最近日志:"
    tail -5 "$LOG_DIR/superset.log"
    exit 0
fi

nohup .venv-superset/bin/superset run -h 0.0.0.0 -p 8088 --with-threads \
    > "$LOG_DIR/superset.log" 2>&1 &
sleep 10
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/login/)
echo "Superset 状态码: $code"
echo "看板地址: http://192.168.0.109:8088/superset/dashboard/4/  (admin / admin123)"
echo "日志文件: $LOG_DIR/superset.log"
echo "最近日志:"
tail -5 "$LOG_DIR/superset.log"
