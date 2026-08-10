"""项目/品类监测范围与自动采集计划的持久化仓储。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


def _scope_id(brand_id: str, city: str, mall_name: str, category: str) -> str:
    value = f"{brand_id}|{city}|{mall_name}|{category}".encode("utf-8")
    return f"scope_{hashlib.sha256(value).hexdigest()[:24]}"


class MonitoringScopeRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in (
            "created_at",
            "updated_at",
            "latest_indicator_date",
            "latest_dianping_date",
            "latest_xiaohongshu_date",
        ):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def register(
        self,
        *,
        brand_id: str,
        city: str,
        mall_name: str,
        category: str,
        data_origin: str = "external_webbridge",
    ) -> Dict[str, Any]:
        scope_id = _scope_id(brand_id, city, mall_name, category)
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO monitoring_scopes
                        (scope_id, brand_id, city, mall_name, category, data_origin)
                    VALUES
                        (:scope_id, :brand_id, :city, :mall_name, :category, :data_origin)
                    ON CONFLICT (brand_id, city, mall_name, category) DO UPDATE SET
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """
                ),
                {
                    "scope_id": scope_id,
                    "brand_id": brand_id,
                    "city": city,
                    "mall_name": mall_name,
                    "category": category,
                    "data_origin": data_origin,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def get(self, scope_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT scope.*,
                           indicator.latest_indicator_date,
                           dianping.latest_dianping_date,
                           xiaohongshu.latest_xiaohongshu_date
                    FROM monitoring_scopes AS scope
                    LEFT JOIN LATERAL (
                        SELECT MAX(stat_date) AS latest_indicator_date
                        FROM brand_indicators_daily
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND mall_name = scope.mall_name
                    ) AS indicator ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MAX(crawl_date) AS latest_dianping_date
                        FROM dp_shop_metrics
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND place = scope.mall_name
                    ) AS dianping ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MAX(crawl_date) AS latest_xiaohongshu_date
                        FROM xhs_notes
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND COALESCE(mall_name, '') = scope.mall_name
                    ) AS xiaohongshu ON TRUE
                    WHERE scope.scope_id = :scope_id
                    """
                ),
                {"scope_id": scope_id},
            ).mappings().first()
        return self._row(row) if row else None

    def list(self, *, active_only: bool = True) -> List[Dict[str, Any]]:
        where = "WHERE scope.is_active = TRUE" if active_only else ""
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT scope.*,
                           indicator.latest_indicator_date,
                           dianping.latest_dianping_date,
                           xiaohongshu.latest_xiaohongshu_date
                    FROM monitoring_scopes AS scope
                    LEFT JOIN LATERAL (
                        SELECT MAX(stat_date) AS latest_indicator_date
                        FROM brand_indicators_daily
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND mall_name = scope.mall_name
                    ) AS indicator ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MAX(crawl_date) AS latest_dianping_date
                        FROM dp_shop_metrics
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND place = scope.mall_name
                    ) AS dianping ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT MAX(crawl_date) AS latest_xiaohongshu_date
                        FROM xhs_notes
                        WHERE brand_id = scope.brand_id
                          AND city = scope.city
                          AND COALESCE(mall_name, '') = scope.mall_name
                    ) AS xiaohongshu ON TRUE
                    {where}
                    ORDER BY scope.city, scope.mall_name, scope.category, scope.created_at
                    """
                )
            ).mappings().all()
        return [self._row(row) for row in rows]


class CrawlScheduleRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in (
            "created_at",
            "updated_at",
            "last_enqueued_at",
            "last_success_at",
            "last_enqueued_for",
        ):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        *,
        scope_id: str,
        interval_minutes: int = 1440,
        run_hour: int = 9,
        run_minute: int = 0,
        timezone: str = "Asia/Shanghai",
        enabled: bool = False,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        schedule_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO crawl_schedules
                        (schedule_id, scope_id, interval_minutes, run_hour, run_minute,
                         timezone, enabled, max_attempts)
                    VALUES
                        (:schedule_id, :scope_id, :interval_minutes, :run_hour, :run_minute,
                         :timezone, :enabled, :max_attempts)
                    RETURNING *
                    """
                ),
                {
                    "schedule_id": schedule_id,
                    "scope_id": scope_id,
                    "interval_minutes": interval_minutes,
                    "run_hour": run_hour,
                    "run_minute": run_minute,
                    "timezone": timezone,
                    "enabled": enabled,
                    "max_attempts": max_attempts,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def list(self) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT schedule.*, scope.city, scope.mall_name, scope.category, scope.brand_id
                    FROM crawl_schedules AS schedule
                    JOIN monitoring_scopes AS scope ON scope.scope_id = schedule.scope_id
                    ORDER BY schedule.created_at DESC
                    """
                )
            ).mappings().all()
        return [self._row(row) for row in rows]

    def get(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM crawl_schedules WHERE schedule_id = :schedule_id"),
                {"schedule_id": schedule_id},
            ).mappings().first()
        return self._row(row) if row else None

    def update(self, schedule_id: str, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {
            "interval_minutes",
            "run_hour",
            "run_minute",
            "timezone",
            "enabled",
            "max_attempts",
        }
        payload = {key: value for key, value in values.items() if key in allowed}
        if not payload:
            return self.get(schedule_id)
        assignments = [f"{key} = :{key}" for key in payload]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        payload["schedule_id"] = schedule_id
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"UPDATE crawl_schedules SET {', '.join(assignments)} "
                    "WHERE schedule_id = :schedule_id RETURNING *"
                ),
                payload,
            ).mappings().first()
            conn.commit()
        return self._row(row) if row else None

    def delete(self, schedule_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM crawl_schedules WHERE schedule_id = :schedule_id"),
                {"schedule_id": schedule_id},
            )
            conn.commit()
        return bool(result.rowcount)

    def claim_due(self) -> List[Dict[str, Any]]:
        """原子地领取到期计划，避免多个后端进程重复入队。"""
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    UPDATE crawl_schedules AS schedule
                    SET last_enqueued_at = CURRENT_TIMESTAMP,
                        last_enqueued_for =
                            (CURRENT_TIMESTAMP AT TIME ZONE schedule.timezone)::date,
                        last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    FROM monitoring_scopes AS scope
                    WHERE schedule.scope_id = scope.scope_id
                      AND schedule.enabled = TRUE
                      AND scope.is_active = TRUE
                      AND (
                          schedule.last_enqueued_for IS NULL
                          OR schedule.last_enqueued_for <
                              (CURRENT_TIMESTAMP AT TIME ZONE schedule.timezone)::date
                      )
                      AND (CURRENT_TIMESTAMP AT TIME ZONE schedule.timezone)::time >=
                          make_time(schedule.run_hour, schedule.run_minute, 0)
                    RETURNING schedule.*, scope.brand_id, scope.city, scope.mall_name, scope.category
                    """
                )
            ).mappings().all()
            conn.commit()
        return [self._row(row) for row in rows]

    def record_result(self, schedule_id: str, *, success: bool, error: Optional[str] = None) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE crawl_schedules
                    SET last_success_at = CASE WHEN :success THEN CURRENT_TIMESTAMP ELSE last_success_at END,
                        last_error = :error,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE schedule_id = :schedule_id
                    """
                ),
                {"schedule_id": schedule_id, "success": success, "error": error},
            )
            conn.commit()
