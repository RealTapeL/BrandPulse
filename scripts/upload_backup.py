#!/usr/bin/env python3
"""把已通过 pg_restore 校验的备份上传到配置的对象存储。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from brandpulse.storage.object_storage import ObjectStorage


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：.venv/bin/python scripts/upload_backup.py <backup.dump>", file=sys.stderr)
        return 2
    backup = Path(sys.argv[1]).resolve()
    if not backup.is_file():
        print(f"备份不存在：{backup}", file=sys.stderr)
        return 2
    timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key = "backups/postgres/" + timestamp + "/" + backup.name
    uri = ObjectStorage().put_file(backup, key)
    print(f"[BrandPulse backup] 已上传对象存储：{uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
