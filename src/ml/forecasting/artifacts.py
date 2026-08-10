"""模型工件定位，避免 API/Worker 各自拼接不安全路径。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .training import MODEL_ROOT


def find_model_dir(model_id: str) -> Path:
    if not model_id or "/" in model_id or "\\" in model_id:
        raise ValueError("非法模型 ID")
    for metadata_path in MODEL_ROOT.rglob("metadata.json"):
        try:
            metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if metadata.get("model_id") == model_id:
            return metadata_path.parent
    raise FileNotFoundError(f"模型不存在: {model_id}")
