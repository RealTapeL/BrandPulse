-- ============================================================
-- BrandPulse 咖啡品牌情报系统 - 数据库表结构
-- 兼容 MySQL / PostgreSQL
-- 设计原则：实体表 + 关系/指标时序表 + Chunk文档表
-- ============================================================

-- -----------------------------
-- 1. 分类字典表
-- -----------------------------
CREATE TABLE category_dict (
    category_id     VARCHAR(32) PRIMARY KEY COMMENT '分类编码',
    category_l1     VARCHAR(64) NOT NULL COMMENT '一级业态，如餐饮业态',
    category_l2     VARCHAR(64) NOT NULL COMMENT '二级品类，如休闲餐饮',
    category_l3     VARCHAR(64) COMMENT '三级细分，如咖啡',
    level           INT NOT NULL COMMENT '层级 1/2/3',
    description     VARCHAR(255) COMMENT '分类说明',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

COMMENT ON TABLE category_dict IS '品牌分类体系字典';

INSERT INTO category_dict (category_id, category_l1, category_l2, category_l3, level, description) VALUES
('FB_CAFE', '餐饮业态', '休闲餐饮', '咖啡', 3, '咖啡饮品'),
('FB_TEA', '餐饮业态', '休闲餐饮', '茶饮', 3, '茶饮饮品'),
('FB_BAKERY', '餐饮业态', '休闲餐饮', '烘焙甜品', 3, '烘焙甜品');


-- -----------------------------
-- 2. 品牌基础表（实体表）
-- -----------------------------
CREATE TABLE brands (
    brand_id            VARCHAR(32) PRIMARY KEY COMMENT '品牌唯一标识，如 LK001',
    brand_name_cn       VARCHAR(128) NOT NULL COMMENT '品牌中文名',
    brand_name_en       VARCHAR(128) COMMENT '品牌英文名',
    category_id         VARCHAR(32) COMMENT '关联分类字典',
    tier                VARCHAR(32) COMMENT '档次：高端/轻奢/快时尚/大众/平价',
    brand_level         VARCHAR(32) COMMENT '品牌级别：首店/旗舰店/概念店/标准店',
    business_model      VARCHAR(32) COMMENT '经营模式：直营/加盟/联营/直营+加盟',
    
    founding_year       INT COMMENT '成立年份',
    headquarters        VARCHAR(128) COMMENT '总部城市',
    company_name        VARCHAR(255) COMMENT '所属公司',
    company_id          VARCHAR(32) COMMENT '关联公司表',
    
    positioning         TEXT COMMENT '品牌定位描述',
    target_customer     VARCHAR(255) COMMENT '目标客群',
    avg_price_min       DECIMAL(10,2) COMMENT '人均消费下限',
    avg_price_max       DECIMAL(10,2) COMMENT '人均消费上限',
    standard_area_min   DECIMAL(10,2) COMMENT '标准店面积下限（㎡）',
    standard_area_max   DECIMAL(10,2) COMMENT '标准店面积上限（㎡）',
    
    store_count_national INT COMMENT '全国门店总数',
    store_count_city     INT COMMENT '本城市门店数',
    expansion_status     VARCHAR(32) COMMENT '拓店状态：活跃拓店/谨慎拓店/收缩/区域保护',
    
    official_website     VARCHAR(255) COMMENT '品牌官网',
    wechat_official      VARCHAR(128) COMMENT '微信公众号',
    logo_url             VARCHAR(255) COMMENT '品牌LOGO',
    
    data_source          VARCHAR(255) COMMENT '数据来源',
    is_active            BOOLEAN DEFAULT TRUE COMMENT '是否有效',
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (category_id) REFERENCES category_dict(category_id)
);

COMMENT ON TABLE brands IS '品牌基础信息主表';


-- -----------------------------
-- 3. 公司/集团表（实体表）
-- -----------------------------
CREATE TABLE companies (
    company_id      VARCHAR(32) PRIMARY KEY COMMENT '公司唯一标识',
    company_name    VARCHAR(255) NOT NULL COMMENT '公司中文名',
    company_name_en VARCHAR(255) COMMENT '公司英文名',
    headquarters    VARCHAR(128) COMMENT '总部城市',
    founding_year   INT COMMENT '成立年份',
    stock_code      VARCHAR(64) COMMENT '股票代码',
    industry        VARCHAR(128) COMMENT '所属行业',
    description     TEXT COMMENT '公司简介',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

COMMENT ON TABLE companies IS '品牌所属公司/集团信息';


-- -----------------------------
-- 4. 门店表（实体表）
-- -----------------------------
CREATE TABLE stores (
    store_id        VARCHAR(64) PRIMARY KEY COMMENT '门店唯一标识',
    brand_id        VARCHAR(32) NOT NULL COMMENT '关联品牌',
    store_name      VARCHAR(255) COMMENT '门店名称',
    
    province        VARCHAR(64) COMMENT '省份',
    city            VARCHAR(64) COMMENT '城市',
    district        VARCHAR(64) COMMENT '区县',
    mall_name       VARCHAR(255) COMMENT '商场名称',
    address         VARCHAR(512) COMMENT '详细地址',
    floor           VARCHAR(32) COMMENT '楼层',
    
    longitude       DECIMAL(12, 8) COMMENT '经度',
    latitude        DECIMAL(12, 8) COMMENT '纬度',
    store_area      DECIMAL(10, 2) COMMENT '门店面积（㎡）',
    
    opening_date    DATE COMMENT '开业日期',
    closing_date    DATE COMMENT '关店日期',
    store_status    VARCHAR(32) COMMENT '门店状态：营业中/围挡/停业/关闭',
    store_type      VARCHAR(32) COMMENT '门店类型：直营/加盟',
    
    is_our_mall     BOOLEAN DEFAULT FALSE COMMENT '是否本商场门店',
    is_main_store   BOOLEAN DEFAULT FALSE COMMENT '是否旗舰店/主力店',
    
    data_source     VARCHAR(255) COMMENT '数据来源',
    source_url      VARCHAR(512) COMMENT '来源链接',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE stores IS '品牌门店布局信息';

CREATE INDEX idx_stores_brand ON stores(brand_id);
CREATE INDEX idx_stores_city ON stores(city);
CREATE INDEX idx_stores_mall ON stores(mall_name);


-- -----------------------------
-- 5. 品牌指标时序表（核心）
-- -----------------------------
CREATE TABLE brand_metrics (
    metric_id       VARCHAR(64) PRIMARY KEY COMMENT '指标记录ID',
    brand_id        VARCHAR(32) NOT NULL COMMENT '关联品牌',
    metric_date     DATE NOT NULL COMMENT '指标日期',
    
    -- 热度指标
    platform        VARCHAR(64) COMMENT '数据平台：大众点评/小红书/高德',
    overall_score   DECIMAL(3, 2) COMMENT '综合评分',
    taste_score     DECIMAL(3, 2) COMMENT '口味评分',
    env_score       DECIMAL(3, 2) COMMENT '环境评分',
    service_score   DECIMAL(3, 2) COMMENT '服务评分',
    review_count    INT COMMENT '评论数',
    avg_price       DECIMAL(10, 2) COMMENT '人均消费',
    
    -- 布局指标
    store_count     INT COMMENT '门店总数',
    city_count      INT COMMENT '覆盖城市数',
    new_store_count INT COMMENT '新增门店数',
    close_store_count INT COMMENT '关闭门店数',
    
    -- 舆情指标
    social_mentions INT COMMENT '社交讨论量',
    sentiment_positive DECIMAL(5, 2) COMMENT '正面情感占比',
    sentiment_negative DECIMAL(5, 2) COMMENT '负面情感占比',
    top_keywords    VARCHAR(512) COMMENT '热门关键词，逗号分隔',
    
    data_source     VARCHAR(255) COMMENT '数据来源',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE brand_metrics IS '品牌热度、口碑、布局等时序指标';

CREATE INDEX idx_bm_brand_date ON brand_metrics(brand_id, metric_date);
CREATE INDEX idx_bm_platform ON brand_metrics(platform);


-- -----------------------------
-- 6. 门店经营数据表（内部数据）
-- -----------------------------
CREATE TABLE store_operations (
    op_id           VARCHAR(64) PRIMARY KEY COMMENT '经营记录ID',
    store_id        VARCHAR(64) NOT NULL COMMENT '关联门店',
    brand_id        VARCHAR(32) NOT NULL COMMENT '关联品牌',
    record_date     DATE NOT NULL COMMENT '记录日期',
    
    sales_amount    DECIMAL(15, 2) COMMENT '销售额（元）',
    order_count     INT COMMENT '订单数',
    customer_price  DECIMAL(10, 2) COMMENT '客单价（元）',
    customer_flow   INT COMMENT '客流人数',
    
    rent            DECIMAL(15, 2) COMMENT '月租金（元）',
    property_fee    DECIMAL(15, 2) COMMENT '物业费（元）',
    energy_cost     DECIMAL(15, 2) COMMENT '能耗费用（元）',
    store_area      DECIMAL(10, 2) COMMENT '门店面积（㎡）',
    
    rent_to_sales_ratio DECIMAL(5, 2) COMMENT '租售比（%）',
    sales_per_sqm   DECIMAL(15, 2) COMMENT '坪效（元/㎡/月）',
    
    contract_start  DATE COMMENT '合同开始日',
    contract_end    DATE COMMENT '合同到期日',
    is_in_contract  BOOLEAN DEFAULT TRUE COMMENT '是否在合同期内',
    
    data_source     VARCHAR(255) COMMENT '数据来源：POS/ERP/手工',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (store_id) REFERENCES stores(store_id),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE store_operations IS '门店内部经营数据，用于计算坪效、租售比等';

CREATE INDEX idx_so_store_date ON store_operations(store_id, record_date);
CREATE INDEX idx_so_brand_date ON store_operations(brand_id, record_date);


-- -----------------------------
-- 7. 品牌联系人表（招商用）
-- -----------------------------
CREATE TABLE brand_contacts (
    contact_id      VARCHAR(64) PRIMARY KEY COMMENT '联系人ID',
    brand_id        VARCHAR(32) NOT NULL COMMENT '关联品牌',
    contact_name    VARCHAR(64) COMMENT '联系人姓名',
    contact_title   VARCHAR(64) COMMENT '职位',
    region          VARCHAR(128) COMMENT '负责区域',
    city_scope      VARCHAR(255) COMMENT '负责城市',
    phone           VARCHAR(32) COMMENT '电话',
    email           VARCHAR(128) COMMENT '邮箱',
    wechat          VARCHAR(64) COMMENT '微信',
    is_primary      BOOLEAN DEFAULT FALSE COMMENT '是否主要联系人',
    cooperation_status VARCHAR(32) COMMENT '合作状态：已合作/洽谈中/潜在',
    last_contact_date DATE COMMENT '上次联系日期',
    follow_up_notes TEXT COMMENT '跟进记录',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE brand_contacts IS '品牌招商联系人信息';

CREATE INDEX idx_bc_brand ON brand_contacts(brand_id);


-- -----------------------------
-- 8. 竞品/关联品牌关系表
-- -----------------------------
CREATE TABLE brand_relationships (
    relation_id     VARCHAR(64) PRIMARY KEY COMMENT '关系ID',
    brand_id        VARCHAR(32) NOT NULL COMMENT '主体品牌',
    related_brand_id VARCHAR(32) NOT NULL COMMENT '关联品牌',
    relation_type   VARCHAR(32) NOT NULL COMMENT '关系类型：竞品/同集团/互补/上下游',
    confidence_score DECIMAL(3, 2) COMMENT '关系置信度 0-1',
    description     VARCHAR(512) COMMENT '关系说明',
    data_source     VARCHAR(255) COMMENT '数据来源',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id),
    FOREIGN KEY (related_brand_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE brand_relationships IS '品牌间关系网络，如瑞幸 vs 库迪为竞品关系';

CREATE INDEX idx_brand_rel ON brand_relationships(brand_id, relation_type);


-- -----------------------------
-- 9. 知识库 Chunk 表（RAG/LLM 用）
-- -----------------------------
CREATE TABLE knowledge_chunks (
    chunk_id        VARCHAR(64) PRIMARY KEY COMMENT '片段ID',
    entity_type     VARCHAR(32) COMMENT '关联实体类型：brand/store/company',
    entity_id       VARCHAR(64) COMMENT '关联实体ID',
    chunk_type      VARCHAR(32) COMMENT '片段类型：news/report/review/official',
    title           VARCHAR(255) COMMENT '标题',
    content         TEXT COMMENT '文本内容',
    content_vector  VECTOR(1536) COMMENT '向量（PostgreSQL + pgvector，可选）',
    source_url      VARCHAR(512) COMMENT '来源链接',
    source_date     DATE COMMENT '来源日期',
    sentiment       VARCHAR(16) COMMENT '情感：positive/negative/neutral',
    keywords        VARCHAR(512) COMMENT '关键词',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (entity_id) REFERENCES brands(brand_id)
);

COMMENT ON TABLE knowledge_chunks IS '非结构化知识片段，供大模型RAG检索用';

CREATE INDEX idx_kc_entity ON knowledge_chunks(entity_type, entity_id);
CREATE INDEX idx_kc_type ON knowledge_chunks(chunk_type);


-- -----------------------------
-- 10. 数据血缘/采集日志表
-- -----------------------------
CREATE TABLE data_source_logs (
    log_id          VARCHAR(64) PRIMARY KEY COMMENT '日志ID',
    source_name     VARCHAR(128) COMMENT '数据源名称',
    source_type     VARCHAR(32) COMMENT '类型：api/crawler/manual/import',
    entity_type     VARCHAR(32) COMMENT '采集对象：brand/store/metric',
    record_count    INT COMMENT '采集记录数',
    status          VARCHAR(32) COMMENT '状态：success/failed/partial',
    error_message   TEXT COMMENT '错误信息',
    executed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE data_source_logs IS '数据采集日志，用于监控数据更新状态';


-- ============================================================
-- 示例数据：瑞幸、库迪、星巴克
-- ============================================================

INSERT INTO brands (
    brand_id, brand_name_cn, brand_name_en, category_id, tier, brand_level,
    business_model, founding_year, headquarters, company_name,
    positioning, target_customer, avg_price_min, avg_price_max,
    store_count_national, store_count_city, expansion_status,
    official_website, wechat_official, data_source
) VALUES
('LK001', '瑞幸咖啡', 'Luckin Coffee', 'FB_CAFE', '大众', '标准店', '直营+加盟', 2017, '厦门', '瑞幸咖啡（中国）有限公司', '快取咖啡，高性价比，数字化运营', '年轻白领、学生', 9.90, 25.00, 18000, 120, '活跃拓店', 'www.lkcoffee.com', 'luckincoffee', '官网/高德'),
('KD001', '库迪咖啡', 'Cotti Coffee', 'FB_CAFE', '平价', '标准店', '加盟', 2022, '天津', '库迪咖啡（天津）有限公司', '低价咖啡，快速扩张，紧跟瑞幸', '价格敏感人群', 6.90, 15.00, 7000, 45, '活跃拓店', 'www.cotticoffee.com', 'cotticoffee', '官网/高德'),
('SB001', '星巴克', 'Starbucks', 'FB_CAFE', '高端', '旗舰店', '直营', 1971, '西雅图', '星巴克企业管理（中国）有限公司', '第三空间，社交场景，精品咖啡', '商务人士、中产', 30.00, 45.00, 7000, 80, '谨慎拓店', 'www.starbucks.com.cn', '星巴克中国', '官网/高德');

INSERT INTO brand_relationships (relation_id, brand_id, related_brand_id, relation_type, confidence_score, description) VALUES
('REL_LK_KD_001', 'LK001', 'KD001', '竞品', 0.95, '库迪贴身竞争瑞幸，价格带接近'),
('REL_LK_SB_001', 'LK001', 'SB001', '竞品', 0.70, '同属咖啡赛道，但价格带和场景差异大'),
('REL_KD_SB_001', 'KD001', 'SB001', '竞品', 0.55, '价格带差异大，竞争关系较弱');
