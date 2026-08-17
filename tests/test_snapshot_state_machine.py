"""Phase 1 快照状态、来源即时关联和范围约束回归测试。"""

from brandpulse.storage.trusted_data_repository import (
    CollectionRunRepository,
    SnapshotRepository,
    TrustedScopeRepository,
)
from brandpulse.db_clients.postgres_client import PostgresClient
from sqlalchemy import text
from fastapi.testclient import TestClient

from brandpulse.api.app import app
from tests.conftest import AUTH_HEADERS


def test_collection_creates_snapshot_and_source_result_before_finalize():
    scope = TrustedScopeRepository().list()[0]
    collection = CollectionRunRepository().create(
        scope_id=scope["scope_id"],
        crawl_job_id=None,
        trigger_type="migration",
    )
    collection_run_id = collection["collection_run_id"]
    snapshot_id = collection["snapshot_id"]
    try:
        snapshots = SnapshotRepository()
        draft = snapshots.get(snapshot_id)
        assert draft["status"] == "draft"
        assert draft["scope_id"] == scope["scope_id"]
        assert draft["collection_run_id"] == collection_run_id
        assert draft["status_history"][-1]["to_status"] == "draft"

        assert CollectionRunRepository().mark_collecting(collection_run_id) is True
        collecting = snapshots.get(snapshot_id)
        assert collecting["status"] == "collecting"
        assert [item["to_status"] for item in collecting["status_history"]][-2:] == [
            "draft",
            "collecting",
        ]

        source_name = "dianping_webbridge"
        source_run = CollectionRunRepository().start_source_run(collection_run_id, source_name)
        CollectionRunRepository().finish_source_run(
            source_run["source_run_id"],
            status="empty_validated",
            record_count=0,
            validated_count=0,
            raw_saved_count=0,
            failure_reason="测试空结果",
            metadata={"test": True},
        )
        in_progress = snapshots.get(snapshot_id)
        source_result = next(
            item for item in in_progress["source_results"] if item["source_name"] == source_name
        )
        assert source_result["status"] == "empty_validated"
        assert source_result["failure_reason"] == "测试空结果"

        failed = snapshots.finalize_collection(collection_run_id)
        assert failed["status"] == "failed"
        assert [item["to_status"] for item in failed["status_history"]][-2:] == [
            "validating",
            "failed",
        ]
    finally:
        with PostgresClient().engine.begin() as conn:
            conn.execute(
                text("DELETE FROM data_snapshots WHERE snapshot_id = :snapshot_id"),
                {"snapshot_id": snapshot_id},
            )
            conn.execute(
                text("DELETE FROM collection_runs WHERE collection_run_id = :collection_run_id"),
                {"collection_run_id": collection_run_id},
            )


def test_snapshot_history_api_returns_a_real_snapshot_history():
    scope = TrustedScopeRepository().list()[0]
    snapshot = SnapshotRepository().latest_released(scope["scope_id"])
    if not snapshot:
        return
    response = TestClient(app, headers=AUTH_HEADERS).get(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/history"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == snapshot["snapshot_id"]
    assert payload["items"]
    assert payload["items"][-1]["to_status"] in {"ready", "published"}
