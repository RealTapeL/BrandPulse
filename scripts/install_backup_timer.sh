#!/usr/bin/env bash
# 安装当前用户的每日数据库备份 timer；不会申请 root 权限。
set -Eeuo pipefail

cd "$(dirname "$0")/.."
project_root="$(pwd)"
expected_root="$(realpath "${HOME}/BrandPulse")"
[[ "$project_root" == "$expected_root" ]] || {
    printf '[BrandPulse backup][ERROR] systemd 模板使用 %%h/BrandPulse，当前项目位于 %s\n' "$project_root" >&2
    printf '请先修改 deploy/systemd/brandpulse-backup.service 中的路径。\n' >&2
    exit 1
}
command -v systemctl >/dev/null 2>&1 || {
    printf '[BrandPulse backup][ERROR] 当前系统没有 systemctl\n' >&2
    exit 1
}

systemd_user_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
mkdir -p "$systemd_user_dir" "$project_root/backups/postgres"
install -m 0644 deploy/systemd/brandpulse-backup.service "$systemd_user_dir/"
install -m 0644 deploy/systemd/brandpulse-backup.timer "$systemd_user_dir/"
systemctl --user daemon-reload
systemctl --user enable --now brandpulse-backup.timer
systemctl --user list-timers brandpulse-backup.timer --no-pager
