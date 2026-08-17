"""可信范围、快照门禁和指标语义的回归测试。"""

from brandpulse.indicators.snapshot_metrics import bayesian_weight, is_comparable_cumulative_stock
from brandpulse.storage.trusted_data_repository import (
    SnapshotRepository,
    compatibility_dataset_key,
    scope_key,
)


def _source(*, name: str, required: bool, status: str, observations: int, allow_empty: bool = False):
    return {
        "source_name": name,
        "required": required,
        "allow_empty": allow_empty,
        "status": status,
        "observation_count": observations,
    }


def test_scope_key_separates_category_from_legacy_dataset_identifier():
    coffee_scope = scope_key("苏州", "苏州中心", "咖啡")
    tea_scope = scope_key("苏州", "苏州中心", "茶饮")

    assert coffee_scope != tea_scope
    assert compatibility_dataset_key("苏州", "苏州中心", "咖啡").startswith("MALL_")
    assert "MALL_" not in coffee_scope


def test_snapshot_requires_real_raw_observations_not_connector_claims():
    coverage = {"sources": [_source(
        name="dianping_webbridge", required=True, status="success", observations=0,
    )]}

    assert SnapshotRepository._status(coverage) == (
        "failed", "F", "raw_only", "没有任何来源写入可验证的原始观测",
    )


def test_optional_source_failure_keeps_explicit_dianping_single_source_view():
    coverage = {"sources": [
        _source(name="dianping_webbridge", required=True, status="success", observations=5),
        _source(name="xiaohongshu_webbridge", required=False, status="failed", observations=0, allow_empty=True),
    ]}

    status, grade, mode, reason = SnapshotRepository._status(coverage)

    assert (status, grade, mode, reason) == ("ready", "C", "dianping_single_source", "")


def test_cumulative_stock_trend_rejects_source_failure_irregular_interval_and_decline():
    assert is_comparable_cumulative_stock(
        current_total=110, previous_total=100, interval_days=2, current_source_success=True,
    )
    assert not is_comparable_cumulative_stock(
        current_total=110, previous_total=100, interval_days=8, current_source_success=True,
    )
    assert not is_comparable_cumulative_stock(
        current_total=90, previous_total=100, interval_days=2, current_source_success=True,
    )
    assert not is_comparable_cumulative_stock(
        current_total=110, previous_total=100, interval_days=2, current_source_success=False,
    )


def test_bayesian_weight_uses_recorded_comparison_pool_parameters():
    result = bayesian_weight(score=5.0, review_count=10, average=4.0, threshold=10)

    assert result == 4.5
