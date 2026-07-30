#!/bin/bash
# 启动自研数据看板（FastAPI + Vue3，后台运行，日志写入项目 logs/ 目录）
# 用法: bash scripts/start_web.sh
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

if pgrep -f "uvicorn brandpulse.api.app:app" > /dev/null; then
    echo "看板已在运行: http://192.168.0.109:8000/"
    echo "最近日志:"
    tail -5 "$LOG_DIR/web.log"
    exit 0
fi

nohup env PYTHONPATH="$PROJECT_ROOT/src/backend" .venv/bin/python -m uvicorn brandpulse.api.app:app \
    --host 0.0.0.0 --port 8000 > "$LOG_DIR/web.log" 2>&1 &

# 等待服务就绪（最多 15 秒）
code=""
for i in $(seq 1 15); do
    sleep 1
    code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/dashboard)
    [ "$code" = "200" ] && break
done
echo "看板接口状态码: $code"
echo "看板地址: http://192.168.0.109:8000/"
echo "日志文件: $LOG_DIR/web.log"
echo "最近日志:"
tail -5 "$LOG_DIR/web.log"
