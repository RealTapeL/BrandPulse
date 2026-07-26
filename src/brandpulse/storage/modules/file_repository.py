"""
本地文件缓存仓储

作为 PostgreSQL metrics 存储的轻量级替代/补充。
采集结果以 JSONL 形式写入 data/processed/，无需数据库服务即可查看和后续分析。

文件命名：
    data/processed/metrics_{metric_date}.jsonl

每一行是一条 metric 记录，可直接用 pandas / jq / Python 读取。
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from brandpulse.config.modules.config import Config
from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)


class FileMetricsRepository:
    """把品牌指标写入本地 JSONL 文件，实现无 DB 本地保存"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Config.METRICS_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, metric_date: str) -> Path:
        return self.cache_dir / f"metrics_{metric_date}.jsonl"

    def upsert_metric(self, metric: Dict) -> bool:
        """
        把单条 metric 写入 JSONL。

        同一 metric_id 视为同一条，会先读取当天文件去重再写回，
        保证 'upsert' 语义。因为数据量小，直接读写整个文件即可。
        """
        metric_date = metric.get("metric_date") or datetime.now().strftime("%Y-%m-%d")
        path = self._file_path(metric_date)

        try:
            records: Dict[str, Dict] = {}
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            mid = item.get("metric_id")
                            if mid:
                                records[mid] = item
                        except json.JSONDecodeError:
                            continue

            records[metric["metric_id"]] = {
                **metric,
                "cached_at": datetime.now().isoformat(),
            }

            with open(path, "w", encoding="utf-8") as f:
                for item in records.values():
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

            return True
        except Exception as e:
            logger.error(f"写入本地 metric 缓存失败: {e}")
            return False

    def list_metrics(
        self,
        brand_id: Optional[str] = None,
        platform: Optional[str] = None,
        metric_date: Optional[str] = None,
    ) -> List[Dict]:
        """读取本地缓存的指标列表"""
        results = []

        if metric_date:
            files = [self._file_path(metric_date)]
        else:
            files = sorted(self.cache_dir.glob("metrics_*.jsonl"))

        for path in files:
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if brand_id and item.get("brand_id") != brand_id:
                        continue
                    if platform and item.get("platform") != platform:
                        continue
                    results.append(item)

        return sorted(results, key=lambda x: x.get("cached_at", ""), reverse=True)


def is_db_disabled() -> bool:
    """通过环境变量控制是否禁用 PostgreSQL metrics 写入"""
    return os.getenv("DISABLE_METRICS_DB", "").lower() in ("1", "true", "yes")
