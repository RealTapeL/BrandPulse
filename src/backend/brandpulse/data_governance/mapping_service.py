"""映射决策与受影响快照回算编排。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from brandpulse.indicators.snapshot_metrics import SnapshotMetricService
from brandpulse.storage.master_data_repository import MasterDataRepository


class MappingService:
    """人工映射落库后，按台账逐个重算同一快照的正式指标。"""

    def __init__(self):
        self.repo = MasterDataRepository()

    def _run_recalculations(self, result: Dict[str, Any]) -> Dict[str, Any]:
        completed, failed = [], []
        for request in result.get("recalculation_requests", []):
            request_id = str(request["request_id"])
            claimed = self.repo.claim_recalculation_request(request_id)
            if not claimed:
                continue
            try:
                metric_result = SnapshotMetricService().calculate(str(claimed["snapshot_id"]))
                self.repo.finish_recalculation_request(request_id)
                completed.append({"request_id": request_id, "metric_run_id": metric_result["metric_run_id"]})
            except Exception as exc:  # 保留失败台账，让操作人员可重试，不吞掉证据。
                self.repo.finish_recalculation_request(request_id, error_message=str(exc))
                failed.append({"request_id": request_id, "error": str(exc)})
        return {**result, "recalculation": {"completed": completed, "failed": failed}}

    def decide(
        self,
        *,
        observation_id: str,
        mapping_status: str,
        store_id: Optional[str],
        evidence_note: str,
        effective_from: Optional[date],
        actor: str,
    ) -> Dict[str, Any]:
        return self._run_recalculations(self.repo.decide_mapping(
            observation_id=observation_id,
            mapping_status=mapping_status,
            store_id=store_id,
            evidence_note=evidence_note,
            effective_from=effective_from,
            actor=actor,
        ))

    def revert(self, *, mapping_id: str, evidence_note: str, actor: str) -> Dict[str, Any]:
        return self._run_recalculations(self.repo.revert_mapping(
            mapping_id=mapping_id,
            evidence_note=evidence_note,
            actor=actor,
        ))
