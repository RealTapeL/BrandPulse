-- ============================================================
-- BrandPulse 初始化脚本
-- 创建咖啡品牌情报系统核心表
-- ============================================================

-- 分类字典表
CREATE TABLE IF NOT EXISTS category_dict (
    category_id     VARCHAR(32) PRIMARY KEY,
    category_l1     VARCHAR(64) NOT NULL,
    category_l2     VARCHAR(64) NOT NULL,
    category_l3     VARCHAR(64),
    level           INT NOT NULL,
    description     VARCHAR(255)
);

INSERT INTO category_dict (category_id, category_l1, category_l2, category_l3, level, description) VALUES
('FB_CAFE', '餐饮业态', '休闲餐饮', '咖啡', 3, '咖啡饮品'),
('FB_TEA', '餐饮业态', '休闲餐饮', '茶饮', 3, '茶饮饮品'),
('FB_BAKERY', '餐饮业态', '休闲餐饮', '烘焙甜品', 3, '烘焙甜品')
ON CONFLICT (category_id) DO NOTHING;

-- 公司/集团表
CREATE TABLE IF NOT EXISTS companies (
    company_id      VARCHAR(32) PRIMARY KEY,
    company_name    VARCHAR(255) NOT NULL,
    company_name_en VARCHAR(255),
    headquarters    VARCHAR(128),
    founding_year   INT,
    stock_code      VARCHAR(64),
    industry        VARCHAR(128),
    description     TEXT
);

-- 品牌基础表
CREATE TABLE IF NOT EXISTS brands (
    brand_id            VARCHAR(32) PRIMARY KEY,
    brand_name_cn       VARCHAR(128) NOT NULL,
    brand_name_en       VARCHAR(128),
    category_id         VARCHAR(32),
    tier                VARCHAR(32),
    brand_level         VARCHAR(32),
    business_model      VARCHAR(32),
    founding_year       INT,
    headquarters        VARCHAR(128),
    company_name        VARCHAR(255),
    company_id          VARCHAR(32),
    positioning         TEXT,
    target_customer     VARCHAR(255),
    avg_price_min       DECIMAL(10,2),
    avg_price_max       DECIMAL(10,2),
    standard_area_min   DECIMAL(10,2),
    standard_area_max   DECIMAL(10,2),
    store_count_national INT,
    store_count_city     INT,
    expansion_status     VARCHAR(32),
    official_website     VARCHAR(255),
    wechat_official      VARCHAR(128),
    logo_url             VARCHAR(255),
    data_source          VARCHAR(255),
    is_active            BOOLEAN DEFAULT TRUE,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 门店表
CREATE TABLE IF NOT EXISTS stores (
    store_id        VARCHAR(64) PRIMARY KEY,
    brand_id        VARCHAR(32) NOT NULL,
    store_name      VARCHAR(255),
    province        VARCHAR(64),
    city            VARCHAR(64),
    district        VARCHAR(64),
    mall_name       VARCHAR(255),
    address         VARCHAR(512),
    floor           VARCHAR(32),
    longitude       DECIMAL(12, 8),
    latitude        DECIMAL(12, 8),
    store_area      DECIMAL(10, 2),
    opening_date    DATE,
    closing_date    DATE,
    store_status    VARCHAR(32),
    store_type      VARCHAR(32),
    is_our_mall     BOOLEAN DEFAULT FALSE,
    is_main_store   BOOLEAN DEFAULT FALSE,
    data_source     VARCHAR(255),
    source_url      VARCHAR(512),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stores_brand ON stores(brand_id);
CREATE INDEX IF NOT EXISTS idx_stores_city ON stores(city);
CREATE INDEX IF NOT EXISTS idx_stores_mall ON stores(mall_name);

-- 品牌指标时序表
CREATE TABLE IF NOT EXISTS brand_metrics (
    metric_id       VARCHAR(64) PRIMARY KEY,
    brand_id        VARCHAR(32) NOT NULL,
    metric_date     DATE NOT NULL,
    platform        VARCHAR(64),
    overall_score   DECIMAL(3, 2),
    taste_score     DECIMAL(3, 2),
    env_score       DECIMAL(3, 2),
    service_score   DECIMAL(3, 2),
    review_count    INT,
    avg_price       DECIMAL(10, 2),
    store_count     INT,
    city_count      INT,
    new_store_count INT,
    close_store_count INT,
    social_mentions INT,
    sentiment_positive DECIMAL(5, 2),
    sentiment_negative DECIMAL(5, 2),
    top_keywords    VARCHAR(512),
    data_source     VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bm_brand_date ON brand_metrics(brand_id, metric_date);
CREATE INDEX IF NOT EXISTS idx_bm_platform ON brand_metrics(platform);

-- 门店经营数据表
CREATE TABLE IF NOT EXISTS store_operations (
    op_id           VARCHAR(64) PRIMARY KEY,
    store_id        VARCHAR(64) NOT NULL,
    brand_id        VARCHAR(32) NOT NULL,
    record_date     DATE NOT NULL,
    sales_amount    DECIMAL(15, 2),
    order_count     INT,
    customer_price  DECIMAL(10, 2),
    customer_flow   INT,
    rent            DECIMAL(15, 2),
    property_fee    DECIMAL(15, 2),
    energy_cost     DECIMAL(15, 2),
    store_area      DECIMAL(10, 2),
    rent_to_sales_ratio DECIMAL(5, 2),
    sales_per_sqm   DECIMAL(15, 2),
    contract_start  DATE,
    contract_end    DATE,
    is_in_contract  BOOLEAN DEFAULT TRUE,
    data_source     VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_so_store_date ON store_operations(store_id, record_date);
CREATE INDEX IF NOT EXISTS idx_so_brand_date ON store_operations(brand_id, record_date);

-- 品牌联系人表
CREATE TABLE IF NOT EXISTS brand_contacts (
    contact_id      VARCHAR(64) PRIMARY KEY,
    brand_id        VARCHAR(32) NOT NULL,
    contact_name    VARCHAR(64),
    contact_title   VARCHAR(64),
    region          VARCHAR(128),
    city_scope      VARCHAR(255),
    phone           VARCHAR(32),
    email           VARCHAR(128),
    wechat          VARCHAR(64),
    is_primary      BOOLEAN DEFAULT FALSE,
    cooperation_status VARCHAR(32),
    last_contact_date DATE,
    follow_up_notes TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bc_brand ON brand_contacts(brand_id);

-- 品牌关系表
CREATE TABLE IF NOT EXISTS brand_relationships (
    relation_id     VARCHAR(64) PRIMARY KEY,
    brand_id        VARCHAR(32) NOT NULL,
    related_brand_id VARCHAR(32) NOT NULL,
    relation_type   VARCHAR(32) NOT NULL,
    confidence_score DECIMAL(3, 2),
    description     VARCHAR(512),
    data_source     VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_brand_rel ON brand_relationships(brand_id, relation_type);

-- 数据血缘/采集日志表
CREATE TABLE IF NOT EXISTS data_source_logs (
    log_id          VARCHAR(64) PRIMARY KEY,
    source_name     VARCHAR(128),
    source_type     VARCHAR(32),
    entity_type     VARCHAR(32),
    record_count    INT,
    status          VARCHAR(32),
    error_message   TEXT,
    executed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入示例品牌数据
INSERT INTO brands (
    brand_id, brand_name_cn, brand_name_en, category_id, tier, brand_level,
    business_model, founding_year, headquarters, company_name,
    positioning, target_customer, avg_price_min, avg_price_max,
    store_count_national, store_count_city, expansion_status,
    official_website, wechat_official, data_source
) VALUES
('LK001', '瑞幸咖啡', 'Luckin Coffee', 'FB_CAFE', '大众', '标准店', '直营+加盟', 2017, '厦门', '瑞幸咖啡（中国）有限公司', '快取咖啡，高性价比', '年轻白领、学生', 9.90, 25.00, 18000, 120, '活跃拓店', 'www.lkcoffee.com', 'luckincoffee', '初始化'),
('KD001', '库迪咖啡', 'Cotti Coffee', 'FB_CAFE', '平价', '标准店', '加盟', 2022, '天津', '库迪咖啡（天津）有限公司', '低价咖啡，快速扩张', '价格敏感人群', 6.90, 15.00, 7000, 45, '活跃拓店', 'www.cotticoffee.com', 'cotticoffee', '初始化'),
('SB001', '星巴克', 'Starbucks', 'FB_CAFE', '高端', '旗舰店', '直营', 1971, '西雅图', '星巴克企业管理（中国）有限公司', '第三空间，社交场景', '商务人士、中产', 30.00, 45.00, 7000, 80, '谨慎拓店', 'www.starbucks.com.cn', '星巴克中国', '初始化')
ON CONFLICT (brand_id) DO NOTHING;

INSERT INTO brand_relationships (relation_id, brand_id, related_brand_id, relation_type, confidence_score, description) VALUES
('REL_LK_KD_001', 'LK001', 'KD001', '竞品', 0.95, '库迪贴身竞争瑞幸，价格带接近'),
('REL_LK_SB_001', 'LK001', 'SB001', '竞品', 0.70, '同属咖啡赛道，但价格带和场景差异大'),
('REL_KD_SB_001', 'KD001', 'SB001', '竞品', 0.55, '价格带差异大，竞争关系较弱')
ON CONFLICT (relation_id) DO NOTHING;
