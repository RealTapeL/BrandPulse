-- Phase 2：统一指标字典元数据。
-- 只扩展定义表，不改写历史 metric_observations；旧指标事实仍按原版本保留。

ALTER TABLE metric_definitions
    ADD COLUMN IF NOT EXISTS formula TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS comparison_scope VARCHAR(128) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS minimum_sample_size INT NOT NULL DEFAULT 0
        CHECK (minimum_sample_size >= 0),
    ADD COLUMN IF NOT EXISTS quality_requirements JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS allow_alert BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS allow_prediction BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE metric_definitions SET
    formula = CASE metric_key
        WHEN 'dp_review_count_stock' THEN 'SUM(confirmed accepted raw_observations.payload.review_count)'
        WHEN 'dp_store_count_observed' THEN 'COUNT(accepted dp_shop_metric observations)'
        WHEN 'xhs_content_count_observed' THEN 'COUNT(accepted xhs_note observations)'
        WHEN 'xhs_likes_stock' THEN 'SUM(known likes; missing likes are excluded)'
        WHEN 'bayesian_reputation' THEN '(v / (v + m)) * R + (m / (v + m)) * C'
        WHEN 'dianping_review_share' THEN 'brand or shop review_count / same scope Dianping review_count'
        WHEN 'source_coverage_ratio' THEN 'successful expected sources / expected sources'
        WHEN 'entity_mapping_coverage' THEN 'confirmed mapped observations / accepted observations'
        WHEN 'dp_review_count_delta' THEN 'current comparable cumulative reviews - previous comparable snapshot'
        WHEN 'dp_review_count_growth_rate' THEN 'review delta / previous comparable cumulative reviews'
        ELSE formula
    END,
    comparison_scope = CASE metric_key
        WHEN 'bayesian_reputation' THEN 'same mall × same category → same city × same category'
        WHEN 'dianping_review_share' THEN 'same scope × same source × same snapshot'
        WHEN 'source_coverage_ratio' THEN 'snapshot expected sources'
        WHEN 'entity_mapping_coverage' THEN 'same scope × same snapshot'
        WHEN 'dp_review_count_delta' THEN 'same scope × same source × comparable adjacent snapshot'
        WHEN 'dp_review_count_growth_rate' THEN 'same scope × same source × comparable adjacent snapshot'
        ELSE 'same scope × same snapshot'
    END,
    minimum_sample_size = CASE metric_key
        WHEN 'bayesian_reputation' THEN 3
        WHEN 'dianping_review_share' THEN 1
        WHEN 'dp_review_count_growth_rate' THEN 2
        ELSE 0
    END,
    quality_requirements = CASE metric_key
        WHEN 'bayesian_reputation' THEN '{"requires_score": true, "requires_positive_review_count": true, "minimum_pool": 3}'::jsonb
        WHEN 'dianping_review_share' THEN '{"required_source": "dianping_webbridge", "missing_source_is_not_zero": true}'::jsonb
        WHEN 'dp_review_count_delta' THEN '{"requires_two_comparable_snapshots": true, "max_interval_days": 7, "cumulative_decline_is_not_comparable": true}'::jsonb
        WHEN 'dp_review_count_growth_rate' THEN '{"requires_two_comparable_snapshots": true, "max_interval_days": 7, "cumulative_decline_is_not_comparable": true}'::jsonb
        WHEN 'source_coverage_ratio' THEN '{"failed_source_is_not_success": true, "empty_validated_is_not_success": true}'::jsonb
        ELSE quality_requirements
    END,
    allow_alert = metric_key IN ('source_coverage_ratio', 'entity_mapping_coverage', 'dp_review_count_growth_rate'),
    allow_prediction = metric_key IN ('dp_review_count_delta', 'dp_review_count_growth_rate'),
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO metric_definitions (
    metric_key, display_name, metric_group, description, unit, source_scope, window_rule,
    metric_version, formula, comparison_scope, minimum_sample_size, quality_requirements,
    allow_alert, allow_prediction
) VALUES
    ('dp_content_count_delta', '点评观测门店增量', 'activity', '两个可比快照之间的点评观测门店数量变化；门店映射变化时不输出趋势结论。', '家', '点评 · 当前范围', '相邻可比快照', 'snapshot-v2', 'current observed stores - previous observed stores', 'same scope × same source × comparable adjacent snapshot', 2, '{"requires_two_comparable_snapshots": true}'::jsonb, TRUE, FALSE),
    ('xhs_content_count_delta', '小红书内容增量', 'activity', '两个均成功且可比较的小红书快照之间的公开内容数变化；来源缺失不按零补齐。', '篇', '小红书 · 当前范围', '相邻可比快照', 'snapshot-v2', 'current content count - previous content count', 'same scope × same source × comparable adjacent snapshot', 2, '{"required_source": "xiaohongshu_webbridge", "missing_source_is_not_zero": true}'::jsonb, TRUE, TRUE),
    ('xhs_interaction_delta', '小红书互动增量', 'activity', '两个均成功且互动字段可用的小红书快照之间的互动变化。', '赞', '小红书 · 当前范围', '相邻可比快照', 'snapshot-v2', 'current known likes - previous known likes', 'same scope × same source × comparable adjacent snapshot', 2, '{"requires_known_likes": true}'::jsonb, TRUE, TRUE),
    ('brand_review_share', '品牌点评评价份额', 'competition', '已确认品牌的点评累计评价数 / 当前范围全部点评累计评价数。', '比例', '点评 · 已确认品牌', '当前快照', 'snapshot-v2', 'confirmed brand review count / same scope review count', 'same scope × same source × same snapshot', 1, '{"requires_confirmed_brand_mapping": true}'::jsonb, FALSE, FALSE),
    ('brand_content_share', '品牌小红书内容份额', 'competition', '已确认品牌的小红书内容数 / 当前范围成功小红书内容数。', '比例', '小红书 · 已确认品牌', '当前快照', 'snapshot-v2', 'confirmed brand content count / same scope content count', 'same scope × same source × same snapshot', 1, '{"requires_confirmed_brand_mapping": true, "missing_source_is_not_zero": true}'::jsonb, FALSE, FALSE),
    ('brand_interaction_share', '品牌小红书互动份额', 'competition', '已确认品牌的小红书互动量 / 当前范围成功小红书互动量。', '比例', '小红书 · 已确认品牌', '当前快照', 'snapshot-v2', 'confirmed brand interactions / same scope interactions', 'same scope × same source × same snapshot', 1, '{"requires_confirmed_brand_mapping": true, "missing_source_is_not_zero": true}'::jsonb, FALSE, FALSE),
    ('sample_confidence', '样本置信度', 'quality', '根据样本量和口径完整度给出的数据可用性等级，不代表统计因果置信区间。', '等级', '指标证据', '当前快照', 'snapshot-v2', 'quality requirements + sample size', 'metric-specific comparison pool', 0, '{"must_show_sample_size": true}'::jsonb, FALSE, FALSE),
    ('data_freshness_hours', '数据新鲜度', 'quality', '当前快照观测时间距当前时间的小时数。', '小时', '快照', '当前快照', 'snapshot-v2', 'now - snapshot observed_at', 'same scope × current snapshot', 0, '{"stale_threshold_comes_from_source_requirement": true}'::jsonb, TRUE, FALSE),
    ('mapping_quality', '实体映射质量', 'quality', '已确认实体映射占接受原始观测的比例，并保留待确认数量。', '比例', '原始观测映射', '当前快照', 'snapshot-v2', 'confirmed mapped observations / accepted observations', 'same scope × same snapshot', 1, '{"unmapped_is_not_zero_per_brand": true}'::jsonb, TRUE, FALSE),
    ('consecutive_increase', '连续上升期数', 'trend', '同一指标连续可比快照上升的期数；不可比期间会中断连续性。', '期', '指标快照序列', '近 N 期', 'snapshot-v2', 'count of consecutive valid positive changes', 'same scope × same metric × comparable snapshots', 2, '{"requires_comparable_series": true}'::jsonb, TRUE, FALSE),
    ('consecutive_decline', '连续下降期数', 'trend', '同一指标连续可比快照下降的期数；累计值下降会被标记为不可比。', '期', '指标快照序列', '近 N 期', 'snapshot-v2', 'count of consecutive valid negative changes', 'same scope × same metric × comparable snapshots', 2, '{"requires_comparable_series": true}'::jsonb, TRUE, FALSE),
    ('volatility', '指标波动率', 'trend', '多个可比周期变化率的离散程度；周期不足时不输出。', '比例', '指标快照序列', '近 N 期', 'snapshot-v2', 'standard deviation of comparable period growth rates', 'same scope × same metric × comparable snapshots', 3, '{"requires_three_comparable_points": true}'::jsonb, FALSE, TRUE)
ON CONFLICT (metric_key) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    metric_group = EXCLUDED.metric_group,
    description = EXCLUDED.description,
    unit = EXCLUDED.unit,
    source_scope = EXCLUDED.source_scope,
    window_rule = EXCLUDED.window_rule,
    metric_version = EXCLUDED.metric_version,
    formula = EXCLUDED.formula,
    comparison_scope = EXCLUDED.comparison_scope,
    minimum_sample_size = EXCLUDED.minimum_sample_size,
    quality_requirements = EXCLUDED.quality_requirements,
    allow_alert = EXCLUDED.allow_alert,
    allow_prediction = EXCLUDED.allow_prediction,
    updated_at = CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_metric_definitions_group_active
    ON metric_definitions(metric_group, is_active, metric_key);

GRANT ALL PRIVILEGES ON metric_definitions TO brandpulse;
