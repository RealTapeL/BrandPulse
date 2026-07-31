-- 指标时序表（按品牌聚合后的查询视图）
CREATE TABLE IF NOT EXISTS indicators (
    id          SERIAL PRIMARY KEY,
    brand_id    VARCHAR(32) NOT NULL,
    indicator   VARCHAR(64) NOT NULL,
    date        DATE NOT NULL,
    value       DECIMAL(12, 4) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brand_id, indicator, date)
);

CREATE INDEX IF NOT EXISTS idx_indicators_brand_indicator_date
    ON indicators(brand_id, indicator, date DESC);

GRANT ALL PRIVILEGES ON indicators TO brandpulse;
GRANT ALL PRIVILEGES ON SEQUENCE indicators_id_seq TO brandpulse;
