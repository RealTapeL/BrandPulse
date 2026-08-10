-- ============================================================
-- BrandPulse 初始化脚本
-- 创建咖啡品牌情报系统核心表
-- ============================================================

-- 分类字典表
CREATE TABLE IF NOT EXISTS category_dict (
    category_id     VARCHAR(32) PRIMARY KEY,
    category_l1     VARCHAR(64) NOT NULL,
    category_l2     VARCHAR(64),
    category_l3     VARCHAR(64),
    level           INT NOT NULL,
    description     VARCHAR(255)
);

INSERT INTO category_dict (category_id, category_l1, category_l2, category_l3, level, description) VALUES
    ('RETAIL', '零售业态', NULL, NULL, 1, '购物中心零售业态'),
    ('RETAIL_FASHION', '零售业态', '服装鞋帽', NULL, 2, '服装鞋帽品类'),
    ('RETAIL_FASHION_FAST', '零售业态', '服装鞋帽', '快时尚', 3, '优衣库 / ZARA / H&M / MUJI'),
    ('RETAIL_FASHION_SPORT', '零售业态', '服装鞋帽', '运动休闲', 3, 'Nike / Adidas / 李宁 / 安踏'),
    ('RETAIL_FASHION_LUXURY', '零售业态', '服装鞋帽', '国际精品', 3, 'LV / Gucci / Hermès'),
    ('RETAIL_FASHION_PRELUX', '零售业态', '服装鞋帽', '轻奢', 3, 'Coach / MK / Tory Burch'),
    ('RETAIL_FASHION_WOMEN', '零售业态', '服装鞋帽', '女装', 3, 'ONLY / VERO MODA / 歌莉娅'),
    ('RETAIL_FASHION_MEN', '零售业态', '服装鞋帽', '男装', 3, '海澜之家 / 太平鸟 / GXG'),
    ('RETAIL_FASHION_KIDS', '零售业态', '服装鞋帽', '童装', 3, '巴拉巴拉 / 安踏儿童'),
    ('RETAIL_FASHION_LINGERIE', '零售业态', '服装鞋帽', '内衣/家居服', 3, '曼妮芬 / 蕉内 / ubras'),
    ('RETAIL_JEWELRY', '零售业态', '珠宝配饰', NULL, 2, '珠宝配饰品类'),
    ('RETAIL_JEWELRY_GOLD', '零售业态', '珠宝配饰', '黄金珠宝', 3, '周大福 / 周生生 / 老凤祥'),
    ('RETAIL_JEWELRY_FASHION', '零售业态', '珠宝配饰', '时尚饰品', 3, '施华洛世奇 / 潘多拉 / APM'),
    ('RETAIL_JEWELRY_WATCH', '零售业态', '珠宝配饰', '眼镜/手表', 3, 'JINS / 宝岛 / LOHO'),
    ('RETAIL_BEAUTY', '零售业态', '美妆护肤', NULL, 2, '美妆护肤品类'),
    ('RETAIL_BEAUTY_HIGH', '零售业态', '美妆护肤', '高端护肤', 3, 'Chanel / Dior / SK-II'),
    ('RETAIL_BEAUTY_MASS', '零售业态', '美妆护肤', '大众护肤', 3, '欧莱雅 / 玉兰油 / 珀莱雅'),
    ('RETAIL_BEAUTY_MAKEUP', '零售业态', '美妆护肤', '彩妆香氛', 3, 'MAC / 完美日记 / 花西子'),
    ('RETAIL_BEAUTY_COLLECTION', '零售业态', '美妆护肤', '美妆集合店', 3, '丝芙兰 / 屈臣氏 / 妍丽'),
    ('RETAIL_DIGITAL', '零售业态', '数码电子', NULL, 2, '数码电子品类'),
    ('RETAIL_DIGITAL_PHONE', '零售业态', '数码电子', '手机数码', 3, 'Apple / 华为 / 小米'),
    ('RETAIL_DIGITAL_APPLIANCE', '零售业态', '数码电子', '家电生活电器', 3, '戴森 / 索尼 / 松下'),
    ('RETAIL_DIGITAL_WEARABLE', '零售业态', '数码电子', '智能穿戴', 3, '华为 / 小米 / Apple Watch'),
    ('RETAIL_HOME', '零售业态', '生活家居', NULL, 2, '生活家居品类'),
    ('RETAIL_HOME_FURNITURE', '零售业态', '生活家居', '家具家居', 3, '宜家 / 无印良品 / NITORI'),
    ('RETAIL_HOME_DAILY', '零售业态', '生活家居', '日用百货', 3, '名创优品 / KKV / NOME'),
    ('RETAIL_HOME_TEXTILE', '零售业态', '生活家居', '家纺用品', 3, '罗莱 / 富安娜 / 水星'),
    ('RETAIL_SUPERMARKET', '零售业态', '超市/便利店', NULL, 2, '超市/便利店品类'),
    ('RETAIL_SUPERMARKET_PREMIUM', '零售业态', '超市/便利店', '精品超市', 3, 'Ole'' / City Super / G-Super'),
    ('RETAIL_SUPERMARKET_GENERAL', '零售业态', '超市/便利店', '综合超市', 3, '永辉 / 大润发 / 沃尔玛'),
    ('RETAIL_SUPERMARKET_CONVENIENCE', '零售业态', '超市/便利店', '便利店', 3, '7-11 / 全家 / 罗森'),
    ('FB', '餐饮业态', NULL, NULL, 1, '购物中心餐饮业态'),
    ('FB_DINING', '餐饮业态', '正餐', NULL, 2, '正餐品类'),
    ('FB_DINING_CHINESE', '餐饮业态', '正餐', '中式正餐', 3, '海底捞 / 西贝 / 外婆家'),
    ('FB_DINING_WESTERN', '餐饮业态', '正餐', '西式正餐', 3, '必胜客 / 西提 / 蓝蛙'),
    ('FB_DINING_JAPANKOREA', '餐饮业态', '正餐', '日韩式', 3, '太二 / 九锅一堂 / 姜虎东'),
    ('FB_DINING_HOTPOT', '餐饮业态', '正餐', '火锅', 3, '海底捞 / 小龙坎 / 呷哺呷哺'),
    ('FB_DINING_BBQ', '餐饮业态', '正餐', '烧烤/地方特色', 3, '很久以前 / 南京大牌档'),
    ('FB_FASTFOOD', '餐饮业态', '快餐/轻食', NULL, 2, '快餐/轻食品类'),
    ('FB_FASTFOOD_CHINESE', '餐饮业态', '快餐/轻食', '中式快餐', 3, '老乡鸡 / 真功夫 / 大米先生'),
    ('FB_FASTFOOD_WESTERN', '餐饮业态', '快餐/轻食', '西式快餐', 3, '肯德基 / 麦当劳 / 汉堡王'),
    ('FB_FASTFOOD_LIGHT', '餐饮业态', '快餐/轻食', '轻食/健康餐', 3, 'Wagas / Gaga / 超级碗'),
    ('FB_LEISURE', '餐饮业态', '休闲餐饮', NULL, 2, '休闲餐饮品类'),
    ('FB_CAFE', '餐饮业态', '休闲餐饮', '咖啡', 3, '星巴克 / 瑞幸 / Manner'),
    ('FB_TEA', '餐饮业态', '休闲餐饮', '茶饮', 3, '喜茶 / 奈雪 / 茶百道'),
    ('FB_BAKERY', '餐饮业态', '休闲餐饮', '烘焙甜品', 3, '面包新语 / 好利来 / 哈根达斯'),
    ('FB_FOODCOURT', '餐饮业态', '美食广场', NULL, 2, '美食广场品类'),
    ('FB_FOODCOURT_FOODCOURT', '餐饮业态', '美食广场', '美食广场', 3, '大食代 / 食通天 / 档口集合'),
    ('KIDS', '儿童业态', NULL, NULL, 1, '购物中心儿童业态'),
    ('KIDS_RETAIL', '儿童业态', '儿童零售', NULL, 2, '儿童零售品类'),
    ('KIDS_RETAIL_APPAREL', '儿童业态', '儿童零售', '童装童鞋', 3, '巴拉巴拉 / 安奈儿'),
    ('KIDS_RETAIL_TOYS', '儿童业态', '儿童零售', '玩具用品', 3, '孩子王 / 玩具反斗城'),
    ('KIDS_ENTERTAINMENT', '儿童业态', '儿童娱乐', NULL, 2, '儿童娱乐品类'),
    ('KIDS_ENTERTAINMENT_PLAY', '儿童业态', '儿童娱乐', '游乐园', 3, 'Meland / 卡通尼 / 乐高中心'),
    ('KIDS_EDUCATION', '儿童业态', '儿童教育', NULL, 2, '儿童教育品类'),
    ('KIDS_EDUCATION_TRAINING', '儿童业态', '儿童教育', '早教/培训', 3, '金宝贝 / 美吉姆 / 新东方'),
    ('ENT', '休闲娱乐', NULL, NULL, 1, '购物中心休闲娱乐业态'),
    ('ENT_CINEMA', '休闲娱乐', '影院剧院', NULL, 2, '影院剧院品类'),
    ('ENT_CINEMA_MOVIE', '休闲娱乐', '影院剧院', '影院', 3, '万达影城 / CGV / 百老汇'),
    ('ENT_NIGHTLIFE', '休闲娱乐', '夜生活娱乐', NULL, 2, '夜生活娱乐品类'),
    ('ENT_NIGHTLIFE_KTV', '休闲娱乐', '夜生活娱乐', 'KTV/酒吧/Livehouse', 3, '纯K / 星聚会 / Helens'),
    ('ENT_SPORTS', '休闲娱乐', '游艺健身', NULL, 2, '游艺健身品类'),
    ('ENT_SPORTS_GAME', '休闲娱乐', '游艺健身', '电玩游艺', 3, '大玩家 / 风云再起'),
    ('ENT_SPORTS_FITNESS', '休闲娱乐', '游艺健身', '健身运动', 3, '威尔仕 / 乐刻 / 超级猩猩'),
    ('ENT_SPORTS_ICE', '休闲娱乐', '游艺健身', '冰雪运动', 3, '全明星 / 世纪星'),
    ('ENT_CULTURE', '休闲娱乐', '文创空间', NULL, 2, '文创空间品类'),
    ('ENT_CULTURE_BOOKSTORE', '休闲娱乐', '文创空间', '书店/文创', 3, '西西弗 / 言几又 / 诚品'),
    ('SVC', '生活服务', NULL, NULL, 1, '购物中心生活服务业态'),
    ('SVC_BEAUTY', '生活服务', '美业健康', NULL, 2, '美业健康品类'),
    ('SVC_BEAUTY_HAIR', '生活服务', '美业健康', '美容美发', 3, '丝域 / TONI&GUY'),
    ('SVC_BEAUTY_NAIL', '生活服务', '美业健康', '美甲/SPA', 3, '美甲/SPA'),
    ('SVC_MEDICAL', '生活服务', '医疗健康', NULL, 2, '医疗健康品类'),
    ('SVC_MEDICAL_PHARMACY', '生活服务', '医疗健康', '药店', 3, '海王星辰 / 老百姓'),
    ('SVC_MEDICAL_CLINIC', '生活服务', '医疗健康', '诊所/口腔/体检', 3, '诊所/口腔/体检'),
    ('SVC_CONVENIENCE', '生活服务', '便民服务', NULL, 2, '便民服务业品类'),
    ('SVC_CONVENIENCE_FINANCE', '生活服务', '便民服务', '金融服务', 3, '银行 / 证券网点'),
    ('SVC_CONVENIENCE_LIFE', '生活服务', '便民服务', '生活服务', 3, '洗衣 / 宠物 / 照相'),
    ('SVC_EDUCATION', '生活服务', '成人教育', NULL, 2, '成人教育品类'),
    ('SVC_EDUCATION_TRAINING', '生活服务', '成人教育', '培训教育', 3, '语言 / 考证 / 兴趣'),
    ('EXP', '体验业态', NULL, NULL, 1, '购物中心体验业态'),
    ('EXP_AUTOMOTIVE', '体验业态', '新能源汽车', NULL, 2, '新能源汽车品类'),
    ('EXP_AUTOMOTIVE_SHOWROOM', '体验业态', '新能源汽车', '汽车展厅', 3, '特斯拉 / 蔚来 / 理想 / 小鹏'),
    ('EXP_IMMERSIVE', '体验业态', '沉浸式娱乐', NULL, 2, '沉浸式娱乐品类'),
    ('EXP_IMMERSIVE_GAME', '体验业态', '沉浸式娱乐', '剧本杀/密室/VR/沉浸展', 3, '剧本杀 / 密室 / VR体验 / 沉浸展'),
    ('EXP_CULTURE', '体验业态', '文化艺术', NULL, 2, '文化艺术品类'),
    ('EXP_CULTURE_ART', '体验业态', '文化艺术', '艺术空间/展览/快闪/文创市集', 3, '艺术空间 / 展览 / 快闪 / 文创市集')
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
    search_keywords      VARCHAR(255),
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_store_operations_store_date
    ON store_operations(store_id, record_date);

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

-- 知识库片段表（RAG/LLM 用；向量存 Qdrant，此处仅存文本与元数据）
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id        VARCHAR(64) PRIMARY KEY,
    entity_type     VARCHAR(32),
    entity_id       VARCHAR(64),
    chunk_type      VARCHAR(32),
    title           VARCHAR(255),
    content         TEXT,
    source_url      VARCHAR(512),
    source_date     DATE,
    sentiment       VARCHAR(16),
    keywords        VARCHAR(512),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kc_entity ON knowledge_chunks(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_kc_type ON knowledge_chunks(chunk_type);

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
    official_website, wechat_official, search_keywords, data_source
) VALUES
('LK001', '瑞幸咖啡', 'Luckin Coffee', 'FB_CAFE', '大众', '标准店', '直营+加盟', 2017, '厦门', '瑞幸咖啡（中国）有限公司', '快取咖啡，高性价比', '年轻白领、学生', 9.90, 25.00, 18000, 120, '活跃拓店', 'www.lkcoffee.com', 'luckincoffee', '瑞幸咖啡', '初始化'),
('KD001', '库迪咖啡', 'Cotti Coffee', 'FB_CAFE', '平价', '标准店', '加盟', 2022, '天津', '库迪咖啡（天津）有限公司', '低价咖啡，快速扩张', '价格敏感人群', 6.90, 15.00, 7000, 45, '活跃拓店', 'www.cotticoffee.com', 'cotticoffee', '库迪咖啡', '初始化'),
('SB001', '星巴克', 'Starbucks', 'FB_CAFE', '高端', '旗舰店', '直营', 1971, '西雅图', '星巴克企业管理（中国）有限公司', '第三空间，社交场景', '商务人士、中产', 30.00, 45.00, 7000, 80, '谨慎拓店', 'www.starbucks.com.cn', '星巴克中国', '星巴克', '初始化')
ON CONFLICT (brand_id) DO NOTHING;

INSERT INTO brand_relationships (relation_id, brand_id, related_brand_id, relation_type, confidence_score, description) VALUES
('REL_LK_KD_001', 'LK001', 'KD001', '竞品', 0.95, '库迪贴身竞争瑞幸，价格带接近'),
('REL_LK_SB_001', 'LK001', 'SB001', '竞品', 0.70, '同属咖啡赛道，但价格带和场景差异大'),
('REL_KD_SB_001', 'KD001', 'SB001', '竞品', 0.55, '价格带差异大，竞争关系较弱')
ON CONFLICT (relation_id) DO NOTHING;

-- 机器学习训练运行台账；公开基准模型默认不具备生产资格
CREATE TABLE IF NOT EXISTS ml_training_runs (
    run_id              VARCHAR(64) PRIMARY KEY,
    task                VARCHAR(64) NOT NULL,
    dataset_key         VARCHAR(128) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    rq_job_id           VARCHAR(128),
    parameters          JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics             JSONB,
    artifact_path       TEXT,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'public_benchmark',
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    train_rows          BIGINT,
    validation_rows     BIGINT,
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ml_training_runs
    ADD COLUMN IF NOT EXISTS dataset_upload_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS model_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_ml_training_runs_created
    ON ml_training_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_training_runs_dataset
    ON ml_training_runs(dataset_key, created_at DESC);

-- 机器学习数据输入台账；上传数据与 store_operations 保持隔离
CREATE TABLE IF NOT EXISTS ml_dataset_uploads (
    upload_id           VARCHAR(64) PRIMARY KEY,
    dataset_key         VARCHAR(128) NOT NULL UNIQUE,
    original_filename   VARCHAR(255) NOT NULL,
    stored_path         TEXT,
    file_format         VARCHAR(16) NOT NULL,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'user_upload',
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    sha256              VARCHAR(64),
    row_count           BIGINT,
    store_count         INT,
    item_count          INT,
    min_date            DATE,
    max_date            DATE,
    validation          JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              VARCHAR(16) NOT NULL DEFAULT 'valid',
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_dataset_uploads_created
    ON ml_dataset_uploads(created_at DESC);

-- 机器学习输入、训练和导出操作日志
CREATE TABLE IF NOT EXISTS ml_operation_logs (
    log_id              VARCHAR(64) PRIMARY KEY,
    operation_type      VARCHAR(32) NOT NULL,
    status              VARCHAR(16) NOT NULL,
    level               VARCHAR(16) NOT NULL DEFAULT 'info',
    run_id              VARCHAR(64),
    upload_id           VARCHAR(64),
    export_id           VARCHAR(64),
    message             TEXT NOT NULL,
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_operation_logs_created
    ON ml_operation_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_operation_logs_type
    ON ml_operation_logs(operation_type, created_at DESC);

-- 预测文件导出台账
CREATE TABLE IF NOT EXISTS ml_forecast_exports (
    export_id           VARCHAR(64) PRIMARY KEY,
    run_id              VARCHAR(64),
    model_id            VARCHAR(128) NOT NULL,
    file_format         VARCHAR(16) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    rq_job_id           VARCHAR(128),
    file_path           TEXT,
    row_count           BIGINT,
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_forecast_exports_created
    ON ml_forecast_exports(created_at DESC);

-- 为应用用户 brandpulse 授予表读写权限（与 .env 中配置的用户名一致）
GRANT ALL PRIVILEGES ON SCHEMA public TO brandpulse;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO brandpulse;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO brandpulse;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO brandpulse;
