#!/usr/bin/env bash
# 按文件名顺序应用初始化 SQL 和应用迁移；任意 SQL 出错时立即停止。
set -Eeuo pipefail

cd "$(dirname "$0")/.."
project_root="$(pwd)"

die() { printf '[BrandPulse migrations][ERROR] %s\n' "$*" >&2; exit 1; }
log() { printf '[BrandPulse migrations] %s\n' "$*"; }

command -v psql >/dev/null 2>&1 || die "未安装 PostgreSQL 客户端 psql"

if [[ -n "${BRANDPULSE_PYTHON:-}" ]]; then
    python_bin="$BRANDPULSE_PYTHON"
elif [[ -x "$project_root/.venv/bin/python" ]]; then
    python_bin="$project_root/.venv/bin/python"
else
    python_bin="$(command -v python3 || command -v python || true)"
fi
[[ -n "$python_bin" && -x "$python_bin" ]] || die "未找到可用的 Python 解释器"

config_value() {
    "$python_bin" - "$1" <<'PY'
import sys

sys.path.insert(0, "src/backend")
from brandpulse.config.config import Config

print(getattr(Config, sys.argv[1]))
PY
}

db_host="${POSTGRES_HOST:-$(config_value POSTGRES_HOST)}"
db_port="${POSTGRES_PORT:-$(config_value POSTGRES_PORT)}"
db_user="${POSTGRES_USER:-$(config_value POSTGRES_USER)}"
db_password="${POSTGRES_PASSWORD:-$(config_value POSTGRES_PASSWORD)}"
db_name="${POSTGRES_DB:-$(config_value POSTGRES_DB)}"

sql_files=(
    "$project_root"/brandpulse-infra/init-scripts/*.sql
    "$project_root"/migrations/*.sql
)
[[ -e "${sql_files[0]}" ]] || die "没有找到数据库初始化或迁移文件"

log "开始应用 ${#sql_files[@]} 个 SQL 文件到 $db_name@$db_host:$db_port"
for sql_file in "${sql_files[@]}"; do
    log "应用 ${sql_file#"$project_root"/}"
    PGPASSWORD="$db_password" psql \
        --host "$db_host" \
        --port "$db_port" \
        --username "$db_user" \
        --dbname "$db_name" \
        --no-password \
        --set ON_ERROR_STOP=1 \
        --file "$sql_file" >/dev/null
done
log "数据库初始化与迁移全部成功"
