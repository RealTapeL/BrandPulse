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

init_files=()
bootstrap_check="SELECT to_regclass('public.brands') IS NULL"
bootstrap_needed="$(PGPASSWORD="$db_password" psql \
    --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" \
    --no-password --tuples-only --no-align --command "$bootstrap_check")"
if [[ "$bootstrap_needed" == "t" ]]; then
    init_files=("$project_root"/brandpulse-infra/init-scripts/*.sql)
else
    log "检测到既有核心表，跳过基础建表脚本，仅应用版本化迁移"
fi
migration_files=("$project_root"/migrations/*.sql)
[[ -e "${migration_files[0]}" ]] || die "没有找到版本化迁移文件"

if [[ ${#init_files[@]} -gt 0 ]]; then
    log "开始应用 ${#init_files[@]} 个基础建表脚本到 $db_name@$db_host:$db_port"
    for sql_file in "${init_files[@]}"; do
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
fi

# 旧版本在数据库中已存在但没有迁移台账时，重复执行 ALTER TABLE 会因为历史所有者不同失败。
# 若审计、Agent 任务和数据治理表均存在，说明该库至少已经达到 018 的功能基线；只登记基线，不重放旧 DDL。
PGPASSWORD="$db_password" psql \
    --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" --no-password \
    --set ON_ERROR_STOP=1 --command "
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(128) PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_by VARCHAR(32) NOT NULL DEFAULT 'script'
        );
    " >/dev/null
legacy_baseline="$(PGPASSWORD="$db_password" psql \
    --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" --no-password \
    --tuples-only --no-align --command "
        SELECT to_regclass('public.audit_events') IS NOT NULL
           AND to_regclass('public.agent_tasks') IS NOT NULL
           AND to_regclass('public.data_quality_issues') IS NOT NULL;
    ")"

log "开始检查 ${#migration_files[@]} 个版本化迁移"
for sql_file in "${migration_files[@]}"; do
    version="$(basename "$sql_file")"
    applied="$(PGPASSWORD="$db_password" psql \
        --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" --no-password \
        --tuples-only --no-align --command "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '$version');")"
    if [[ "$applied" == "t" ]]; then
        continue
    fi
    if [[ "$legacy_baseline" == "t" && "$version" < "019_" ]]; then
        log "登记既有功能基线 ${version}（不重放历史 DDL）"
        PGPASSWORD="$db_password" psql \
            --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" --no-password \
            --set ON_ERROR_STOP=1 --command "INSERT INTO schema_migrations(version, applied_by) VALUES ('$version', 'legacy_baseline');" >/dev/null
        continue
    fi
    log "应用 ${sql_file#"$project_root"/}"
    PGPASSWORD="$db_password" psql \
        --host "$db_host" \
        --port "$db_port" \
        --username "$db_user" \
        --dbname "$db_name" \
        --no-password \
        --set ON_ERROR_STOP=1 \
        --file "$sql_file" >/dev/null
    PGPASSWORD="$db_password" psql \
        --host "$db_host" --port "$db_port" --username "$db_user" --dbname "$db_name" --no-password \
        --set ON_ERROR_STOP=1 --command "INSERT INTO schema_migrations(version) VALUES ('$version');" >/dev/null
done
log "数据库初始化与版本化迁移全部成功"
