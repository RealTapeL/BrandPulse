from datetime import date

from brandpulse.storage.trusted_data_repository import RawObservationRepository


class RecordingConnection:
    def __init__(self):
        self.sql = ""
        self.parameters = {}

    def execute(self, statement, parameters):
        self.sql = str(statement)
        self.parameters = parameters


def test_raw_observation_upsert_declares_identity_conflict_target():
    connection = RecordingConnection()

    RawObservationRepository.upsert(
        connection,
        {
            "observation_id": "rawobs_test",
            "scope_id": "scope_test",
            "collection_run_id": "collect_test",
            "source_run_id": "source_test",
            "source_name": "dianping_webbridge",
            "record_type": "dp_shop_metric",
            "source_record_key": "shop_test",
            "source_url": "https://example.invalid/shop_test",
            "legacy_dataset_key": "MALL_test",
            "observed_date": date(2026, 8, 17),
            "raw_category": "咖啡",
            "standard_category": "咖啡",
            "category_mapping_status": "confirmed",
            "entity_mapping_status": "pending",
            "quality_status": "accepted",
            "payload": {"shop_name": "测试门店"},
        },
    )

    assert "ON CONFLICT (" in connection.sql
    assert "source_record_key" in connection.sql
    assert "(COALESCE(scope_id, ''::varchar))" in connection.sql
    assert "DO UPDATE SET" in connection.sql
    assert connection.parameters["source_record_key"] == "shop_test"
