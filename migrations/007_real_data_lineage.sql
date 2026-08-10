-- 真实数据链路修复：原始点评数据和每日指标必须携带完整数据集归属。
-- 执行前置条件：确认下面的重复检查不会抛错；脚本不会删除业务数据。

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM dp_shop_metrics
        GROUP BY shop_name, city, crawl_date, brand_id, COALESCE(place, '')
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'dp_shop_metrics 存在新的复合主键重复数据，请先人工处理';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM brand_indicators_daily
        WHERE brand_id IS NULL OR brand_id = ''
    ) THEN
        RAISE EXCEPTION 'brand_indicators_daily 存在缺少 brand_id 的指标数据，拒绝静默归属';
    END IF;
END $$;

UPDATE dp_shop_metrics SET place = '' WHERE place IS NULL;
ALTER TABLE dp_shop_metrics ALTER COLUMN place SET DEFAULT '';
ALTER TABLE dp_shop_metrics ALTER COLUMN place SET NOT NULL;
ALTER TABLE dp_shop_metrics DROP CONSTRAINT IF EXISTS dp_shop_metrics_pkey;
ALTER TABLE dp_shop_metrics
    ADD CONSTRAINT dp_shop_metrics_pkey PRIMARY KEY (shop_name, city, crawl_date, brand_id, place);

ALTER TABLE brand_indicators_daily ALTER COLUMN brand_id SET NOT NULL;
ALTER TABLE brand_indicators_daily DROP CONSTRAINT IF EXISTS brand_indicators_daily_pkey;
ALTER TABLE brand_indicators_daily
    ADD CONSTRAINT brand_indicators_daily_pkey
    PRIMARY KEY (stat_date, city, mall_name, entity_type, entity_name, brand_id);

-- 自定义公式的真实计算结果，不把公式配置伪装成指标值。
CREATE TABLE IF NOT EXISTS custom_formula_values (
    formula_id  VARCHAR(36) NOT NULL REFERENCES custom_formulas(formula_id) ON DELETE CASCADE,
    brand_id    VARCHAR(32) NOT NULL,
    stat_date   DATE NOT NULL,
    value       NUMERIC(18, 6) NOT NULL,
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (formula_id, brand_id, stat_date)
);

CREATE INDEX IF NOT EXISTS idx_formula_values_brand_date
    ON custom_formula_values(brand_id, stat_date DESC);

GRANT ALL PRIVILEGES ON custom_formula_values TO brandpulse;
