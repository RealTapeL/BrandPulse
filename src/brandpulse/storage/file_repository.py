"""
本地文件缓存仓储

作为 PostgreSQL metrics 存储的轻量级替代/补充。
采集结果以标准 JSON（数组）形式写入 data/processed/，无需数据库服务即可查看和后续分析。

文件命名：
    data/processed/metrics_{metric_date}.json

每个文件是一个 JSON 数组，元素为 metric 记录，可直接用 pandas / Python / 编辑器读取。
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


class FileMetricsRepository:
    """把品牌指标写入本地 JSON 文件，实现无 DB 本地保存"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Config.METRICS_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, metric_date: str) -> Path:
        return self.cache_dir / f"metrics_{metric_date}.json"

    def _load_file(self, path: Path) -> List[Dict]:
        """读取单个 JSON 缓存文件，返回记录列表"""
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取缓存文件失败 {path}: {e}")
            return []

    def upsert_metric(self, metric: Dict) -> bool:
        """
        把单条 metric 写入 JSON 数组文件。

        同一 metric_id 视为同一条，会先读取当天文件去重再写回，
        保证 'upsert' 语义。因为数据量小，直接读写整个文件即可。
        """
        metric_date = metric.get("metric_date") or datetime.now().strftime("%Y-%m-%d")
        path = self._file_path(metric_date)

        try:
            records: Dict[str, Dict] = {}
            for item in self._load_file(path):
                mid = item.get("metric_id")
                if mid:
                    records[mid] = item

            records[metric["metric_id"]] = {
                **metric,
                "cached_at": datetime.now().isoformat(),
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(list(records.values()), f, ensure_ascii=False, indent=2)

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
            files = sorted(self.cache_dir.glob("metrics_*.json"))

        for path in files:
            for item in self._load_file(path):
                if brand_id and item.get("brand_id") != brand_id:
                    continue
                if platform and item.get("platform") != platform:
                    continue
                results.append(item)

        return sorted(results, key=lambda x: x.get("cached_at", ""), reverse=True)


def is_db_disabled() -> bool:
    """通过环境变量控制是否禁用 PostgreSQL metrics 写入"""
    return os.getenv("DISABLE_METRICS_DB", "").lower() in ("1", "true", "yes")
