-- Phase 2：修正指标字典中与实际计算实现不一致的口径文字。
-- 点评累计评价是范围级公开存量，允许使用已接受但尚未完成实体映射的原始观测；
-- 实体映射只决定品牌归因，不应把范围级公开存量误写成 confirmed-only。

UPDATE metric_definitions
SET formula = 'SUM(accepted raw_observations.payload.review_count within snapshot; mapping is not required for scope stock)',
    minimum_sample_size = 0,
    quality_requirements = '{"required_source": "dianping_webbridge", "accepted_observations_only": true, "brand_attribution_requires_confirmed_mapping": true}'::jsonb,
    updated_at = CURRENT_TIMESTAMP
WHERE metric_key = 'dp_review_count_stock';

UPDATE metric_definitions
SET minimum_sample_size = 2,
    updated_at = CURRENT_TIMESTAMP
WHERE metric_key = 'dp_review_count_delta';
