"""机器学习训练运行台账仓储。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient


class MLTrainingRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ("parameters", "metrics"):
            item[key] = item.get(key) or {}
        for key in ("created_at", "started_at", "finished_at", "updated_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        dataset_key: str,
        parameters: Dict[str, Any],
        *,
        data_origin: str = "public_benchmark",
        production_eligible: bool = False,
        dataset_upload_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO ml_training_runs
                        (run_id, task, dataset_key, dataset_upload_id, parameters,
                         data_origin, production_eligible)
                    VALUES
                        (:run_id, 'store_sales_forecast', :dataset_key, :dataset_upload_id,
                         CAST(:parameters AS jsonb), :data_origin, :production_eligible)
                    RETURNING *
                    """
                ),
                {
                    "run_id": run_id,
                    "dataset_key": dataset_key,
                    "dataset_upload_id": dataset_upload_id,
                    "parameters": json.dumps(parameters, ensure_ascii=False),
                    "data_origin": data_origin,
                    "production_eligible": production_eligible,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ml_training_runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).mappings().first()
        return self._row(row) if row else None

    def list(self, *, status: Optional[str], limit: int, offset: int) -> Dict[str, Any]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            conditions.append("status = :status")
            params["status"] = status
        where = " AND ".join(conditions)
        with self.client.engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM ml_training_runs WHERE {where}"), params
            ).scalar_one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT * FROM ml_training_runs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
        return {"items": [self._row(row) for row in rows], "total": int(total)}

    def set_rq_job(self, run_id: str, rq_job_id: str) -> None:
        self._update(run_id, rq_job_id=rq_job_id)

    def mark_running(self, run_id: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE ml_training_runs
                    SET status = 'running',
                        started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = :run_id AND status IN ('pending', 'running')
                    """
                ),
                {"run_id": run_id},
            )
            conn.commit()
        return bool(result.rowcount)

    def finish_success(
        self,
        run_id: str,
        *,
        artifact_path: str,
        model_id: str,
        metrics: Dict[str, Any],
        train_rows: int,
        validation_rows: int,
    ) -> None:
        self._update(
            run_id,
            status="success",
            artifact_path=artifact_path,
            model_id=model_id,
            metrics=json.dumps(metrics, ensure_ascii=False),
            train_rows=train_rows,
            validation_rows=validation_rows,
            error=None,
            finished=True,
        )

    def finish_failure(self, run_id: str, error: str) -> None:
        self._update(run_id, status="failed", error=error, finished=True)

    def _update(self, run_id: str, **values: Any) -> None:
        finished = bool(values.pop("finished", False))
        assignments = ["updated_at = CURRENT_TIMESTAMP"]
        params: Dict[str, Any] = {"run_id": run_id}
        for key, value in values.items():
            if key == "metrics" and value is not None:
                assignments.append("metrics = CAST(:metrics AS jsonb)")
            else:
                assignments.append(f"{key} = :{key}")
            params[key] = value
        if finished:
            assignments.append("finished_at = CURRENT_TIMESTAMP")
        with self.client.engine.connect() as conn:
            conn.execute(
                text(f"UPDATE ml_training_runs SET {', '.join(assignments)} WHERE run_id = :run_id"),
                params,
            )
            conn.commit()


class MLDatasetRepository:
    """上传数据集台账。上传文件不会写入 store_operations。"""

    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["validation"] = item.get("validation") or {}
        for key in ("min_date", "max_date", "created_at", "updated_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(
        self,
        *,
        upload_id: str,
        dataset_key: str,
        original_filename: str,
        file_format: str,
        status: str = "validating",
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO ml_dataset_uploads
                        (upload_id, dataset_key, original_filename, file_format, status, error)
                    VALUES (:upload_id, :dataset_key, :original_filename, :file_format, :status, :error)
                    RETURNING *
                    """
                ),
                {
                    "upload_id": upload_id,
                    "dataset_key": dataset_key,
                    "original_filename": original_filename,
                    "file_format": file_format,
                    "status": status,
                    "error": error,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def get(self, upload_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ml_dataset_uploads WHERE upload_id = :upload_id"),
                {"upload_id": upload_id},
            ).mappings().first()
        return self._row(row) if row else None

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM ml_dataset_uploads
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [self._row(row) for row in rows]

    def mark_valid(
        self,
        upload_id: str,
        *,
        stored_path: str,
        sha256: str,
        validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE ml_dataset_uploads
                    SET stored_path = :stored_path,
                        sha256 = :sha256,
                        row_count = :row_count,
                        store_count = :store_count,
                        item_count = :item_count,
                        min_date = :min_date,
                        max_date = :max_date,
                        validation = CAST(:validation AS jsonb),
                        status = 'valid',
                        error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE upload_id = :upload_id
                    RETURNING *
                    """
                ),
                {
                    "upload_id": upload_id,
                    "stored_path": stored_path,
                    "sha256": sha256,
                    "row_count": validation.get("rows"),
                    "store_count": validation.get("stores"),
                    "item_count": validation.get("items"),
                    "min_date": validation.get("min_date"),
                    "max_date": validation.get("max_date"),
                    "validation": json.dumps(validation, ensure_ascii=False),
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def mark_failed(self, upload_id: str, error: str) -> None:
        with self.client.engine.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ml_dataset_uploads
                    SET status = 'failed', error = :error, updated_at = CURRENT_TIMESTAMP
                    WHERE upload_id = :upload_id
                    """
                ),
                {"upload_id": upload_id, "error": error},
            )
            conn.commit()

    def delete(self, upload_id: str) -> None:
        """按精确 ID 清理测试或管理员明确删除的数据集台账。"""
        with self.client.engine.connect() as conn:
            conn.execute(
                text("DELETE FROM ml_operation_logs WHERE upload_id = :upload_id"),
                {"upload_id": upload_id},
            )
            conn.execute(
                text("DELETE FROM ml_dataset_uploads WHERE upload_id = :upload_id"),
                {"upload_id": upload_id},
            )
            conn.commit()


class MLOperationLogRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["details"] = item.get("details") or {}
        if item.get("created_at") is not None:
            item["created_at"] = str(item["created_at"])
        return item

    def append(
        self,
        *,
        operation_type: str,
        status: str,
        message: str,
        level: str = "info",
        run_id: Optional[str] = None,
        upload_id: Optional[str] = None,
        export_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        log_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO ml_operation_logs
                        (log_id, operation_type, status, level, run_id, upload_id,
                         export_id, message, details)
                    VALUES
                        (:log_id, :operation_type, :status, :level, :run_id, :upload_id,
                         :export_id, :message, CAST(:details AS jsonb))
                    RETURNING *
                    """
                ),
                {
                    "log_id": log_id,
                    "operation_type": operation_type,
                    "status": status,
                    "level": level,
                    "run_id": run_id,
                    "upload_id": upload_id,
                    "export_id": export_id,
                    "message": message,
                    "details": json.dumps(details or {}, ensure_ascii=False, default=str),
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def list(
        self,
        *,
        operation_type: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        conditions = ["1=1"]
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if operation_type:
            conditions.append("operation_type = :operation_type")
            params["operation_type"] = operation_type
        where = " AND ".join(conditions)
        with self.client.engine.connect() as conn:
            total = conn.execute(
                text(f"SELECT COUNT(*) FROM ml_operation_logs WHERE {where}"), params
            ).scalar_one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT * FROM ml_operation_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
        return {"items": [self._row(row) for row in rows], "total": int(total)}


class MLExportRepository:
    def __init__(self):
        self.client = PostgresClient()

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ("created_at", "started_at", "finished_at", "updated_at"):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item

    def create(self, *, model_id: str, file_format: str, run_id: Optional[str]) -> Dict[str, Any]:
        export_id = str(uuid4())
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO ml_forecast_exports
                        (export_id, run_id, model_id, file_format)
                    VALUES (:export_id, :run_id, :model_id, :file_format)
                    RETURNING *
                    """
                ),
                {
                    "export_id": export_id,
                    "run_id": run_id,
                    "model_id": model_id,
                    "file_format": file_format,
                },
            ).mappings().one()
            conn.commit()
        return self._row(row)

    def get(self, export_id: str) -> Optional[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ml_forecast_exports WHERE export_id = :export_id"),
                {"export_id": export_id},
            ).mappings().first()
        return self._row(row) if row else None

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.client.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM ml_forecast_exports
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
        return [self._row(row) for row in rows]

    def set_rq_job(self, export_id: str, rq_job_id: str) -> None:
        self._update(export_id, rq_job_id=rq_job_id)

    def mark_running(self, export_id: str) -> bool:
        return self._update_status(export_id, "running")

    def finish_success(self, export_id: str, *, file_path: str, row_count: int) -> None:
        self._update(
            export_id,
            status="success",
            file_path=file_path,
            row_count=row_count,
            error=None,
            finished_at=True,
        )

    def finish_failure(self, export_id: str, error: str) -> None:
        self._update(export_id, status="failed", error=error, finished_at=True)

    def _update_status(self, export_id: str, status: str) -> bool:
        with self.client.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE ml_forecast_exports
                    SET status = :status,
                        started_at = CASE WHEN :status = 'running'
                                          THEN COALESCE(started_at, CURRENT_TIMESTAMP)
                                          ELSE started_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE export_id = :export_id AND status IN ('pending', 'running')
                    """
                ),
                {"export_id": export_id, "status": status},
            )
            conn.commit()
        return bool(result.rowcount)

    def _update(self, export_id: str, **values: Any) -> None:
        finished = bool(values.pop("finished_at", False))
        assignments = ["updated_at = CURRENT_TIMESTAMP"]
        params: Dict[str, Any] = {"export_id": export_id}
        for key, value in values.items():
            assignments.append(f"{key} = :{key}")
            params[key] = value
        if finished:
            assignments.append("finished_at = CURRENT_TIMESTAMP")
        with self.client.engine.connect() as conn:
            conn.execute(
                text(
                    f"UPDATE ml_forecast_exports SET {', '.join(assignments)} "
                    "WHERE export_id = :export_id"
                ),
                params,
            )
            conn.commit()
