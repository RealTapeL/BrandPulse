-- =====================================================
-- BrandPulse 商场营运数据模型扩展
-- 维度表 / 原始数据表 / 聚合表（对应 docs/品牌热度布局分布_数据表设计.drawio）
-- 目标：品牌热度、布局、分布
-- =====================================================

-- -----------------------------------------------------
-- 1. 维度表：商场主数据
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS malls (
    mall_id         VARCHAR(64) PRIMARY KEY,
    mall_name       VARCHAR(255) NOT NULL,
    city            VARCHAR(64),
    district        VARCHAR(64),
    business_area   VARCHAR(128),
    address         VARCHAR(512),
    longitude       DECIMAL(12, 8),
    latitude        DECIMAL(12, 8),
    is_our_mall     BOOLEAN DEFAULT FALSE,
    data_source     VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_malls_city ON malls(city);
CREATE INDEX IF NOT EXISTS idx_malls_name ON malls(mall_name);

-- -----------------------------------------------------
-- 2. 原始数据表：小红书笔记（爬虫直接写入）
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS xhs_notes (
    note_id         VARCHAR(64) PRIMARY KEY,
    brand_id        VARCHAR(32) NOT NULL,
    city            VARCHAR(64),
    mall_name       VARCHAR(255),
    title           VARCHAR(512),
    author_name     VARCHAR(255),
    likes           INT,
    publish_time    VARCHAR(64),
    note_url        VARCHAR(512),
    keyword         VARCHAR(255),
    crawl_date      DATE NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_xhs_brand_date ON xhs_notes(brand_id, crawl_date);
CREATE INDEX IF NOT EXISTS idx_xhs_city ON xhs_notes(city);

-- -----------------------------------------------------
-- 3. 原始数据表：大众点评门店指标（爬虫直接写入）
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dp_shop_metrics (
    shop_name       VARCHAR(255) NOT NULL,
    city            VARCHAR(64) NOT NULL,
    crawl_date      DATE NOT NULL,
    brand_id        VARCHAR(32) NOT NULL,
    place           VARCHAR(255) NOT NULL DEFAULT '',
    score           DECIMAL(4, 2),
    review_count    INT,
    avg_price       DECIMAL(10, 2),
    business_area   VARCHAR(128),
    shop_text       TEXT,
    source_url      VARCHAR(512),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (shop_name, city, crawl_date, brand_id, place)
);

CREATE INDEX IF NOT EXISTS idx_dp_brand_date ON dp_shop_metrics(brand_id, crawl_date);
CREATE INDEX IF NOT EXISTS idx_dp_place ON dp_shop_metrics(place);

-- -----------------------------------------------------
-- 4. 聚合表：品牌热度（每日由原始表汇总，AI Agent 主查询入口）
--    每个 品牌×城市×商场×日期×平台 一行
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS brand_heat_daily (
    stat_date       DATE NOT NULL,
    brand_id        VARCHAR(32) NOT NULL,
    city            VARCHAR(64) NOT NULL,
    mall_name       VARCHAR(255) NOT NULL DEFAULT '',
    platform        VARCHAR(32) NOT NULL,
    mentions        INT,
    total_likes     INT,
    avg_likes       DECIMAL(10, 2),
    max_likes       INT,
    dp_review_count INT,
    dp_shop_count   INT,
    dp_avg_price    DECIMAL(10, 2),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stat_date, brand_id, city, mall_name, platform)
);

CREATE INDEX IF NOT EXISTS idx_heat_brand_date ON brand_heat_daily(brand_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_heat_city ON brand_heat_daily(city);

-- -----------------------------------------------------
-- 5. 分布视图：品牌 × 城市 × 商场 门店数
-- -----------------------------------------------------
CREATE OR REPLACE VIEW brand_distribution AS
SELECT
    brand_id,
    city,
    mall_name,
    COUNT(*) AS shop_count
FROM stores
WHERE store_status IS DISTINCT FROM '闭店'
GROUP BY brand_id, city, mall_name;
