#!/usr/bin/env bash
# BrandPulse 一键启动脚本
#
# 启动：PostgreSQL/Redis 检查、RQ Worker、FastAPI、监控调度、告警调度、Vite 前端、WebBridge。
# 已有其他项目占用端口时自动选择备用端口，不会杀掉或覆盖其他进程。
#
# 用法：
#   bash scripts/start_all.sh
#   bash scripts/start_all.sh restart
#   bash scripts/start_all.sh status
#   bash scripts/start_all.sh stop
#
set -Eeuo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$LOG_DIR/pids"
RUNTIME_FILE="$PID_DIR/ports.env"
APP_SIGNATURE_FILE="$PID_DIR/app.signature"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

mkdir -p "$LOG_DIR" "$PID_DIR"
export PATH="$HOME/.local/node/bin:$PATH"

log() { printf '[BrandPulse] %s\n' "$*"; }
warn() { printf '[BrandPulse][WARN] %s\n' "$*" >&2; }
die() { printf '[BrandPulse][ERROR] %s\n' "$*" >&2; exit 1; }

app_signature() {
    # 只计算应用源代码、运行配置和启动子脚本的内容摘要，不输出任何配置内容。
    # 这样即使存在未提交修改，下一次 start 也会刷新旧进程；.env 只参与哈希，不会写入日志。
    local path
    {
        for path in \
            "src/backend" \
            "src/frontend/src" \
            "src/frontend/index.html" \
            "src/frontend/vite.config.js" \
            "src/frontend/package.json" \
            "requirements.txt" \
            ".env" \
            "scripts/start_rq_worker.sh" \
            "scripts/start_monitoring_scheduler.sh" \
            "scripts/start_alert_scheduler.sh"; do
            if [[ -d "$path" ]]; then
                find "$path" -type d -name '__pycache__' -prune -o -type f -print0 \
                    | sort -z \
                    | xargs -0 -r sha256sum
            elif [[ -f "$path" ]]; then
                sha256sum "$path"
            fi
        done
    } | sha256sum | awk '{print $1}'
}

[[ -x "$VENV_PYTHON" ]] || die "缺少 .venv，请先执行：python -m venv .venv && .venv/bin/pip install -r requirements.txt"

config_value() {
    "$VENV_PYTHON" - "$1" <<'PY'
import sys
sys.path.insert(0, "src/backend")
from brandpulse.config.config import Config

name = sys.argv[1]
value = getattr(Config, name)
print(value if value is not None else "")
PY
}

REDIS_URL="${REDIS_URL:-$(config_value REDIS_URL)}"
POSTGRES_HOST="${POSTGRES_HOST:-$(config_value POSTGRES_HOST)}"
POSTGRES_PORT="${POSTGRES_PORT:-$(config_value POSTGRES_PORT)}"
POSTGRES_DB="${POSTGRES_DB:-$(config_value POSTGRES_DB)}"
BACKEND_PORT="${BRANDPULSE_BACKEND_PORT:-8000}"
FRONTEND_PORT="${BRANDPULSE_FRONTEND_PORT:-5173}"
START_WEBBRIDGE="${BRANDPULSE_START_WEBBRIDGE:-1}"
START_MONITORING_SCHEDULER="${BRANDPULSE_START_MONITORING_SCHEDULER:-1}"
START_ALERT_SCHEDULER="${BRANDPULSE_START_ALERT_SCHEDULER:-1}"

if [[ -z "${BRANDPULSE_BACKEND_PORT:-}" && -z "${BRANDPULSE_FRONTEND_PORT:-}" && -f "$RUNTIME_FILE" ]]; then
    # 复用上次自动选择的端口，避免重复执行脚本时前端代理漂移。
    # 该文件只由本脚本写入，内容是两个数字端口变量。
    source "$RUNTIME_FILE"
fi

CURRENT_APP_SIGNATURE="$(app_signature)"
PREVIOUS_APP_SIGNATURE=""
if [[ -f "$APP_SIGNATURE_FILE" ]]; then
    PREVIOUS_APP_SIGNATURE="$(<"$APP_SIGNATURE_FILE")"
fi
REFRESH_APP_PROCESSES=0
if [[ "${1:-start}" == "restart" || "$CURRENT_APP_SIGNATURE" != "$PREVIOUS_APP_SIGNATURE" ]]; then
    REFRESH_APP_PROCESSES=1
fi

pid_file() { printf '%s/%s.pid' "$PID_DIR" "$1"; }

pid_is_alive() {
    local pid_file_path="$1"
    [[ -f "$pid_file_path" ]] || return 1
    local pid
    pid="$(<"$pid_file_path")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null
}

process_args() {
    ps -p "$1" -o args= 2>/dev/null || true
}

process_belongs_to_project() {
    local pid="$1"
    local args
    local process_cwd
    args="$(process_args "$pid")"
    process_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$args" == *"$PROJECT_ROOT"* || "$process_cwd" == "$PROJECT_ROOT" || "$process_cwd" == "$PROJECT_ROOT/"* ]]
}

process_group_leader() {
    ps -o pgid= -p "$1" 2>/dev/null | tr -d ' ' || true
}

normalize_frontend_pid() {
    local pid="$1"
    local process_group_id
    process_group_id="$(process_group_leader "$pid")"
    if [[ "$process_group_id" =~ ^[0-9]+$ ]] \
        && [[ "$(process_args "$process_group_id")" == *"npm run dev"* ]] \
        && process_belongs_to_project "$process_group_id"; then
        printf '%s' "$process_group_id"
    else
        printf '%s' "$pid"
    fi
}

port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltnH "sport = :$port" 2>/dev/null | grep -q .
    elif command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    else
        return 1
    fi
}

port_owner() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltnpH "sport = :$port" 2>/dev/null || true
    elif command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    fi
}

find_free_port() {
    local start="$1"
    local port
    for ((port = start; port <= start + 100; port++)); do
        if ! port_in_use "$port"; then
            printf '%s' "$port"
            return 0
        fi
    done
    return 1
}

start_process() {
    local name="$1"
    shift
    local pid_path
    pid_path="$(pid_file "$name")"

    if pid_is_alive "$pid_path"; then
        local old_pid
        old_pid="$(<"$pid_path")"
        log "$name 已在运行（PID $old_pid），日志：$LOG_DIR/$name.log"
        return 0
    fi
    rm -f "$pid_path"

    if command -v setsid >/dev/null 2>&1; then
        # 所有服务都脱离当前终端，避免启动脚本退出或终端关闭时，
        # uvicorn/worker/npx 的子进程收到挂断信号而提前退出。
        setsid "$@" >"$LOG_DIR/$name.log" 2>&1 < /dev/null &
    else
        nohup "$@" >"$LOG_DIR/$name.log" 2>&1 < /dev/null &
    fi
    local new_pid=$!
    printf '%s\n' "$new_pid" >"$pid_path"
    sleep 1
    if ! kill -0 "$new_pid" 2>/dev/null; then
        warn "$name 启动失败，最近日志："
        tail -20 "$LOG_DIR/$name.log" >&2 || true
        return 1
    fi
    log "$name 已启动（PID $new_pid），日志：$LOG_DIR/$name.log"
}

stop_process() {
    local name="$1"
    local pid_path
    pid_path="$(pid_file "$name")"
    if ! pid_is_alive "$pid_path"; then
        rm -f "$pid_path"
        return 0
    fi
    local pid
    pid="$(<"$pid_path")"
    local args
    args="$(process_args "$pid")"
    if [[ "$name" == "webbridge" && "$args" != *"kimi-webbridge mcp"* ]]; then
        warn "$name 的 PID $pid 不是本脚本启动的 WebBridge，未停止"
        return 0
    fi
    if [[ "$name" != "webbridge" ]] && ! process_belongs_to_project "$pid"; then
        warn "$name 的 PID $pid 不属于当前项目，未停止"
        return 0
    fi
    local process_group_id
    process_group_id="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    kill "$pid" 2>/dev/null || true
    # start_process 使用 setsid 创建独立进程组；同时结束子进程，避免 npm/RQ 子进程残留。
    if [[ "$process_group_id" =~ ^[0-9]+$ && "$process_group_id" == "$pid" ]]; then
        kill -- "-$process_group_id" 2>/dev/null || true
    fi
    for _ in {1..20}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
        if [[ "$name" != "webbridge" ]] && process_belongs_to_project "$pid"; then
            warn "$name 未在 4 秒内退出，发送受控 SIGKILL 以避免新旧代码混用"
            kill -KILL "$pid" 2>/dev/null || true
            if [[ "$process_group_id" =~ ^[0-9]+$ && "$process_group_id" == "$pid" ]]; then
                kill -KILL -- "-$process_group_id" 2>/dev/null || true
            fi
            for _ in {1..10}; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.1
            done
        fi
    fi
    if kill -0 "$pid" 2>/dev/null; then
        warn "$name 仍未退出，保留 PID 文件并终止本次启动"
        return 1
    fi
    rm -f "$pid_path"
    log "$name 已停止"
}

stop_matching_process() {
    local name="$1"
    local pattern="$2"
    local pid
    local pid_path
    pid_path="$(pid_file "$name")"

    # 优先使用本脚本记录的 PID；没有 PID 文件时才通过命令行识别，避免误停其他项目。
    if pid_is_alive "$pid_path"; then
        pid="$(<"$pid_path")"
        if [[ "$name" == "frontend" ]]; then
            pid="$(normalize_frontend_pid "$pid")"
            printf '%s\n' "$pid" >"$pid_path"
        fi
        stop_process "$name"
        return 0
    fi
    pid="$(pgrep -f "$pattern" | head -1 || true)"
    if [[ -n "$pid" ]]; then
        if [[ "$name" == "frontend" ]]; then
            pid="$(normalize_frontend_pid "$pid")"
        fi
        printf '%s\n' "$pid" >"$pid_path"
        stop_process "$name"
    fi
}

status() {
    log "项目目录：$PROJECT_ROOT"
    for name in backend worker monitoring alerts frontend webbridge; do
        local pid_path
        pid_path="$(pid_file "$name")"
        if pid_is_alive "$pid_path"; then
            local pid
            pid="$(<"$pid_path")"
            log "$name: running (PID $pid)"
        else
            log "$name: stopped"
        fi
    done
    log "端口：backend=$BACKEND_PORT frontend=$FRONTEND_PORT webbridge=10086"
    log "日志目录：$LOG_DIR"
}

if [[ "${1:-start}" == "stop" ]]; then
    stop_process webbridge
    stop_process frontend
    stop_process alerts
    stop_process monitoring
    stop_process worker
    stop_process backend
    rm -f "$RUNTIME_FILE" "$APP_SIGNATURE_FILE"
    exit 0
fi

if [[ "${1:-start}" == "status" ]]; then
    status
    exit 0
fi

if [[ "${1:-start}" == "restart" ]]; then
    log "收到 restart 指令，将刷新 BrandPulse 自有应用进程"
elif [[ "${1:-start}" != "start" ]]; then
    die "用法：bash scripts/start_all.sh [start|restart|status|stop]"
fi

if command -v pg_isready >/dev/null 2>&1; then
    if ! pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -d "$POSTGRES_DB" >/dev/null 2>&1; then
        die "PostgreSQL 未就绪（$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB），请先启动数据库"
    fi
else
    warn "未找到 pg_isready，跳过 PostgreSQL 就绪检查；后端启动时会再次验证连接"
fi
log "PostgreSQL 已就绪：$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB"

redis_ready() {
    "$VENV_PYTHON" - "$REDIS_URL" <<'PY' >/dev/null 2>&1
import sys
from redis import Redis
Redis.from_url(sys.argv[1]).ping()
PY
}

if ! redis_ready; then
    if [[ "$REDIS_URL" =~ ^redis://(127\.0\.0\.1|localhost):6379/[0-9]+$ ]] && command -v redis-server >/dev/null 2>&1; then
        log "Redis 未运行，启动本机 Redis：127.0.0.1:6379"
        redis-server --daemonize yes --bind 127.0.0.1 --port 6379 >/dev/null
    else
        die "Redis 未就绪（$REDIS_URL），且无法安全自动启动本机 Redis"
    fi
fi
redis_ready || die "Redis 启动后仍不可用：$REDIS_URL"
log "Redis 已就绪：$REDIS_URL"

# 8000/5173 可能属于其他项目。显式指定端口时严格失败；默认端口冲突则安全顺延。
extract_port() {
    sed -n 's/.*--port[ =]\([0-9][0-9]*\).*/\1/p' <<<"$1" | head -1
}

if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
    if [[ -n "$PREVIOUS_APP_SIGNATURE" ]]; then
        log "检测到应用代码或运行配置变化，刷新旧进程以加载最新代码"
    else
        log "未找到应用版本标记，刷新现有 BrandPulse 进程以建立版本标记"
    fi
    # WebBridge 是外部工具，不随项目源代码变化重启；其余服务都必须重新导入 Python/Vue 代码。
    stop_matching_process frontend '[n]ode .*BrandPulse/src/frontend/node_modules/.bin/vite'
    stop_matching_process alerts '[b]randpulse.alerts.runner'
    stop_matching_process monitoring '[b]randpulse.monitoring.runner'
    stop_matching_process worker '[r]q worker brandpulse-crawl'
    stop_matching_process backend '[u]vicorn brandpulse.api.app:app'
fi

existing_backend_pid="$(pgrep -f '[u]vicorn brandpulse.api.app:app' | head -1 || true)"
if [[ -n "$existing_backend_pid" ]]; then
    existing_backend_port="$(extract_port "$(process_args "$existing_backend_pid")")"
    if [[ -n "$existing_backend_port" ]]; then
        BACKEND_PORT="$existing_backend_port"
        log "检测到已有 BrandPulse 后端（PID $existing_backend_pid），复用端口 $BACKEND_PORT"
    elif [[ -n "${BRANDPULSE_BACKEND_PORT:-}" ]]; then
        die "检测到已有 BrandPulse 后端，但无法从进程参数解析端口"
    else
        die "检测到已有 BrandPulse 后端，但无法解析其监听端口"
    fi
    if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
        die "旧后端进程仍未退出（PID $existing_backend_pid），为避免新旧代码混用，请检查 $LOG_DIR/backend.log"
    fi
    printf '%s\n' "$existing_backend_pid" >"$(pid_file backend)"
elif port_in_use "$BACKEND_PORT"; then
    if [[ -n "${BRANDPULSE_BACKEND_PORT:-}" ]]; then
        warn "后端端口 $BACKEND_PORT 已被占用："
        port_owner "$BACKEND_PORT" >&2
        die "请释放端口或修改 BRANDPULSE_BACKEND_PORT"
    else
        old_port="$BACKEND_PORT"
        BACKEND_PORT="$(find_free_port $((BACKEND_PORT + 1)))" || die "找不到可用后端端口"
        warn "端口 $old_port 已被其他服务占用，BrandPulse 后端改用 $BACKEND_PORT"
        port_owner "$old_port" >&2
    fi
fi

if [[ -z "$existing_backend_pid" ]]; then
    start_process backend env PYTHONPATH="$PROJECT_ROOT/src/backend" \
        "$VENV_PYTHON" -m uvicorn brandpulse.api.app:app \
        --host 0.0.0.0 --port "$BACKEND_PORT"
else
    log "BrandPulse 后端进程已存在，跳过重复启动"
fi

# RQ worker 需要 Redis；代码变化时随应用一起刷新。
existing_worker_pid="$(pgrep -f '[r]q worker brandpulse-crawl' | head -1 || true)"
if [[ -n "$existing_worker_pid" ]]; then
    if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
        die "旧 RQ Worker 仍未退出（PID $existing_worker_pid），请检查 $LOG_DIR/worker.log"
    fi
    printf '%s\n' "$existing_worker_pid" >"$(pid_file worker)"
    log "RQ Worker 已在运行，跳过重复启动"
else
    start_process worker env PYTHONPATH="$PROJECT_ROOT/src/backend" REDIS_URL="$REDIS_URL" \
        "$PROJECT_ROOT/scripts/start_rq_worker.sh"
fi

# 自动采集/报告调度器独立于 FastAPI，后端重启不会中断计划。
if [[ "$START_MONITORING_SCHEDULER" != "0" ]]; then
    existing_monitoring_pid="$(pgrep -f '[b]randpulse.monitoring.runner' | head -1 || true)"
    if [[ -n "$existing_monitoring_pid" ]]; then
        if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
            die "旧 monitoring 调度器仍未退出（PID $existing_monitoring_pid），请检查 $LOG_DIR/monitoring.log"
        fi
        printf '%s\n' "$existing_monitoring_pid" >"$(pid_file monitoring)"
        log "monitoring 调度器已在运行（PID $existing_monitoring_pid），复用现有进程"
    else
        start_process monitoring env PYTHONPATH="$PROJECT_ROOT/src/backend:$PROJECT_ROOT/src" \
            "$PROJECT_ROOT/scripts/start_monitoring_scheduler.sh"
    fi
else
    log "BRANDPULSE_START_MONITORING_SCHEDULER=0，跳过自动采集/报告调度器"
fi

# 告警调度器独立于 FastAPI，避免 API 多副本重复检查和重复通知。
if [[ "$START_ALERT_SCHEDULER" != "0" ]]; then
    existing_alert_pid="$(pgrep -f '[b]randpulse.alerts.runner' | head -1 || true)"
    if [[ -n "$existing_alert_pid" ]]; then
        if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
            die "旧 alerts 调度器仍未退出（PID $existing_alert_pid），请检查 $LOG_DIR/alerts.log"
        fi
        printf '%s\n' "$existing_alert_pid" >"$(pid_file alerts)"
        log "alerts 调度器已在运行（PID $existing_alert_pid），复用现有进程"
    else
        start_process alerts env PYTHONPATH="$PROJECT_ROOT/src/backend:$PROJECT_ROOT/src" \
            "$PROJECT_ROOT/scripts/start_alert_scheduler.sh"
    fi
else
    log "BRANDPULSE_START_ALERT_SCHEDULER=0，跳过告警调度器"
fi

if [[ "$START_WEBBRIDGE" != "0" ]]; then
    if port_in_use 10086; then
        existing_webbridge_pid="$(pgrep -f '[k]imi-webbridge mcp' | head -1 || true)"
        if [[ -n "$existing_webbridge_pid" ]]; then
            printf '%s\n' "$existing_webbridge_pid" >"$(pid_file webbridge)"
        fi
        log "WebBridge 端口 10086 已占用，复用现有服务"
    elif command -v npx >/dev/null 2>&1; then
        start_process webbridge env PATH="$PATH" npx -y kimi-webbridge mcp
        for _ in {1..15}; do
            port_in_use 10086 && break
            sleep 1
        done
        if ! port_in_use 10086; then
            warn "WebBridge 未监听 10086，请查看 $LOG_DIR/webbridge.log；后端和前端仍已启动"
        fi
    else
        warn "未找到 npx，跳过 WebBridge；如需真实点评/小红书采集请安装 Node.js"
    fi
else
    log "BRANDPULSE_START_WEBBRIDGE=0，跳过 WebBridge"
fi

existing_frontend_pid="$(pgrep -f '[n]ode .*BrandPulse/src/frontend/node_modules/.bin/vite' | head -1 || true)"
if [[ -n "$existing_frontend_pid" ]]; then
    existing_frontend_pid="$(normalize_frontend_pid "$existing_frontend_pid")"
    existing_frontend_port="$(extract_port "$(process_args "$existing_frontend_pid")")"
    if [[ -n "$existing_frontend_port" ]]; then
        FRONTEND_PORT="$existing_frontend_port"
        log "检测到已有 BrandPulse 前端（PID $existing_frontend_pid），复用端口 $FRONTEND_PORT"
    else
        die "检测到已有 BrandPulse 前端，但无法解析其监听端口"
    fi
    if [[ "$REFRESH_APP_PROCESSES" == "1" ]]; then
        die "旧前端进程仍未退出（PID $existing_frontend_pid），为避免加载旧代码，请检查 $LOG_DIR/frontend.log"
    fi
    printf '%s\n' "$existing_frontend_pid" >"$(pid_file frontend)"
elif port_in_use "$FRONTEND_PORT"; then
    if [[ -n "${BRANDPULSE_FRONTEND_PORT:-}" ]]; then
        warn "前端端口 $FRONTEND_PORT 已被占用："
        port_owner "$FRONTEND_PORT" >&2
        die "请释放端口或修改 BRANDPULSE_FRONTEND_PORT"
    else
        old_port="$FRONTEND_PORT"
        FRONTEND_PORT="$(find_free_port $((FRONTEND_PORT + 1)))" || die "找不到可用前端端口"
        warn "端口 $old_port 已被其他服务占用，BrandPulse 前端改用 $FRONTEND_PORT"
        port_owner "$old_port" >&2
    fi
fi

if [[ -z "$existing_frontend_pid" ]]; then
    command -v npm >/dev/null 2>&1 || die "未找到 npm，请先安装 Node.js"
    start_process frontend env BRANDPULSE_BACKEND_PORT="$BACKEND_PORT" \
        npm --prefix "$PROJECT_ROOT/src/frontend" run dev -- \
        --host 0.0.0.0 --port "$FRONTEND_PORT"
else
    log "BrandPulse 前端进程已存在，跳过重复启动"
fi

printf 'BACKEND_PORT=%s\nFRONTEND_PORT=%s\n' "$BACKEND_PORT" "$FRONTEND_PORT" >"$RUNTIME_FILE"
printf '%s\n' "$CURRENT_APP_SIGNATURE" >"$APP_SIGNATURE_FILE"
for _ in {1..15}; do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$BACKEND_PORT/api/v1/brands/filters" 2>/dev/null || true)"
    if [[ "$code" != "000" && "$code" =~ ^[0-9]{3}$ ]]; then
        break
    fi
    sleep 1
done

HOST_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk 'NR == 1 { split($4, parts, "/"); print parts[1] }')"
HOST_IP="${HOST_IP:-127.0.0.1}"
log "全部启动流程完成"
log "前端地址：http://$HOST_IP:$FRONTEND_PORT/"
log "后端地址：http://$HOST_IP:$BACKEND_PORT/"
log "如果前端显示 401，请先在登录页获取 BrandPulse 登录令牌"
log "停止服务：bash scripts/start_all.sh stop"
