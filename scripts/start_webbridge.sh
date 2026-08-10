#!/bin/bash
# 启动 Kimi WebBridge MCP 服务（后台运行，日志写入项目 logs/ 目录）
# 前提：Edge 浏览器已打开且安装了 Kimi WebBridge 扩展
# 用法: bash scripts/start_webbridge.sh
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
export PATH="$HOME/.local/node/bin:$PATH"

if pgrep -f "kimi-webbridge mcp" > /dev/null; then
    echo "WebBridge MCP 已在运行: ws://127.0.0.1:10086/ws"
    echo "最近日志:"
    tail -5 "$LOG_DIR/webbridge.log" 2>/dev/null || tail -5 ~/kimi-webbridge.log 2>/dev/null
    exit 0
fi

if command -v setsid >/dev/null 2>&1; then
    # 与 start_all.sh 保持一致：让 WebBridge 脱离当前终端的会话，
    # 避免脚本退出后 npm/npx 子进程收到挂断信号而消失。
    setsid npx -y kimi-webbridge mcp > "$LOG_DIR/webbridge.log" 2>&1 < /dev/null &
else
    nohup npx -y kimi-webbridge mcp > "$LOG_DIR/webbridge.log" 2>&1 < /dev/null &
fi
sleep 8
echo "WebBridge MCP 状态:"
grep -E "WebSocket|状态" "$LOG_DIR/webbridge.log" | head -2
echo "日志文件: $LOG_DIR/webbridge.log"
