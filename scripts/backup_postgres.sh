#!/usr/bin/env bash
# 创建 PostgreSQL custom-format 备份、校验归档并按保留天数清理旧备份。
set -Eeuo pipefail

cd "$(dirname "$0")/.."
project_root="$(pwd)"
venv_python="$project_root/.venv/bin/python"
backup_dir="${BRANDPULSE_BACKUP_DIR:-$project_root/backups/postgres}"
retention_days="${BRANDPULSE_BACKUP_RETENTION_DAYS:-14}"

die() { printf '[BrandPulse backup][ERROR] %s\n' "$*" >&2; exit 1; }
log() { printf '[BrandPulse backup] %s\n' "$*"; }

[[ -x "$venv_python" ]] || die "缺少项目虚拟环境 .venv"
command -v pg_dump >/dev/null 2>&1 || die "未安装 pg_dump"
command -v pg_restore >/dev/null 2>&1 || die "未安装 pg_restore"
[[ "$retention_days" =~ ^[0-9]+$ ]] || die "保留天数必须是正整数"
(( retention_days >= 1 && retention_days <= 3650 )) || die "保留天数必须在 1..3650"

config_value() {
    "$venv_python" - "$1" <<'PY'
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

mkdir -p "$backup_dir"
backup_dir="$(realpath "$backup_dir")"
[[ "$backup_dir" != "/" && "$backup_dir" != "$project_root" ]] \
    || die "备份目录不能是根目录或项目根目录"
if command -v flock >/dev/null 2>&1; then
    exec 9>"$backup_dir/.backup.lock"
    flock -n 9 || die "已有数据库备份正在执行"
fi
timestamp="$(date '+%Y%m%d_%H%M%S')"
final_path="$backup_dir/brandpulse_${timestamp}.dump"
temp_path="$(mktemp "$backup_dir/.brandpulse_${timestamp}.XXXXXX.dump")"
trap 'rm -f "$temp_path"' EXIT

log "开始备份数据库 $db_name -> $final_path"
PGPASSWORD="$db_password" pg_dump \
    --host "$db_host" --port "$db_port" --username "$db_user" \
    --dbname "$db_name" --format custom --compress 6 --no-owner --no-acl \
    --file "$temp_path"
pg_restore --list "$temp_path" >/dev/null
chmod 600 "$temp_path"
mv "$temp_path" "$final_path"
final_name="$(basename "$final_path")"
(cd "$backup_dir" && sha256sum "$final_name" >"$final_name.sha256")
trap - EXIT

find "$backup_dir" -maxdepth 1 -type f -name 'brandpulse_*.dump' \
    -mtime "+$retention_days" -delete
find "$backup_dir" -maxdepth 1 -type f -name 'brandpulse_*.dump.sha256' \
    -mtime "+$retention_days" -delete

size="$(du -h "$final_path" | awk '{print $1}')"
log "备份完成并通过 pg_restore 结构校验：$final_path（$size）"
