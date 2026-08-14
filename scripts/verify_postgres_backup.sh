#!/usr/bin/env bash
# 验证备份校验和与 PostgreSQL custom-format 目录，不写入数据库。
set -Eeuo pipefail

backup_path="${1:-}"
[[ -n "$backup_path" ]] || { printf '用法：bash scripts/verify_postgres_backup.sh <backup.dump>\n' >&2; exit 1; }
[[ -f "$backup_path" ]] || { printf '备份不存在：%s\n' "$backup_path" >&2; exit 1; }
command -v pg_restore >/dev/null 2>&1 || { printf '未安装 pg_restore\n' >&2; exit 1; }

if [[ -f "$backup_path.sha256" ]]; then
    (cd "$(dirname "$backup_path")" && sha256sum --check "$(basename "$backup_path").sha256")
else
    printf '[BrandPulse backup][WARN] 未找到校验和文件，仅验证归档目录\n' >&2
fi
pg_restore --list "$backup_path" >/dev/null
printf '[BrandPulse backup] 备份可读取：%s\n' "$backup_path"
