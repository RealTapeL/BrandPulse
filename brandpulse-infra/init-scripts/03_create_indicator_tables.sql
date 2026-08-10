-- =====================================================
-- BrandPulse 指标计算层数据表
-- 对应 src/backend/brandpulse/indicators/
-- =====================================================

-- -----------------------------------------------------
-- 1. 指标表：门店/商场级 每日计算指标
--    entity_type = 'shop'  -> 门店级（点评数据，entity_name = shop_name）
--    entity_type = 'mall'  -> 商场×品类级（brand_heat_daily 聚合）
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS brand_indicators_daily (
    stat_date       DATE NOT NULL,
    city            VARCHAR(64) NOT NULL,
    mall_name       VARCHAR(255) NOT NULL DEFAULT '',
    entity_type     VARCHAR(16) NOT NULL,
    entity_name     VARCHAR(255) NOT NULL,
    brand_id        VARCHAR(32),
    -- 口碑：贝叶斯加权评分（0~5），解决评价数悬殊导致的评分失真
    weighted_score  NUMERIC(5,3),
    -- 热度：log 归一化加权指数（0~100）
    heat_index      NUMERIC(6,2),
    -- 趋势：周环比动量（本周热度-上周热度)/上周热度
    wow_momentum    NUMERIC(10,4),
    -- 趋势：波动率 = 近 N 期标准差/均值（区分稳定热门与昙花一现）
    volatility      NUMERIC(10,4),
    -- 竞争：声量份额 SOV（0~1），同商场同品类内占比
    sov             NUMERIC(6,4),
    -- 中间计算过程留档（原始值、归一值），保证指标可解释可审计
    detail          JSONB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stat_date, city, mall_name, entity_type, entity_name, brand_id)
);

CREATE INDEX IF NOT EXISTS idx_indicators_entity ON brand_indicators_daily(entity_type, entity_name, stat_date);
CREATE INDEX IF NOT EXISTS idx_indicators_date ON brand_indicators_daily(stat_date);

CREATE TABLE IF NOT EXISTS custom_formulas (
    formula_id  VARCHAR(36) PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(200) NOT NULL DEFAULT '',
    expression  VARCHAR(500) NOT NULL,
    params      JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    remark      VARCHAR(200) NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

GRANT ALL PRIVILEGES ON custom_formulas, custom_formula_values TO brandpulse;
