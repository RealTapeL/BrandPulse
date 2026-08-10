 -- BrandPulse 数据治理：品牌别名、门店匹配、质量问题与采集血缘。
-- 本迁移只新增治理数据和日志字段，不修改或删除现有原始业务数据。

CREATE TABLE IF NOT EXISTS brand_aliases (
    alias_id         VARCHAR(64) PRIMARY KEY,
    brand_id         VARCHAR(32) NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    alias_text       VARCHAR(255) NOT NULL,
    normalized_alias VARCHAR(255) NOT NULL,
    source_name      VARCHAR(128) NOT NULL DEFAULT 'manual',
    status           VARCHAR(16) NOT NULL DEFAULT 'confirmed'
                     CHECK (status IN ('confirmed', 'pending', 'rejected')),
    confidence       NUMERIC(5, 4),
    note             TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_brand_alias_identity
    ON brand_aliases(brand_id, normalized_alias, source_name);
CREATE INDEX IF NOT EXISTS idx_brand_alias_normalized
    ON brand_aliases(normalized_alias, status);

CREATE TABLE IF NOT EXISTS store_aliases (
    alias_id             VARCHAR(64) PRIMARY KEY,
    store_id             VARCHAR(64) REFERENCES stores(store_id) ON DELETE SET NULL,
    brand_id             VARCHAR(32),
    raw_store_name       VARCHAR(255) NOT NULL,
    normalized_store_name VARCHAR(255) NOT NULL,
    city                 VARCHAR(64) NOT NULL DEFAULT '',
    mall_name            VARCHAR(255) NOT NULL DEFAULT '',
    address              VARCHAR(512) NOT NULL DEFAULT '',
    source_name          VARCHAR(128) NOT NULL,
    match_status         VARCHAR(16) NOT NULL DEFAULT 'pending'
                         CHECK (match_status IN ('confirmed', 'pending', 'rejected')),
    match_method         VARCHAR(32) NOT NULL DEFAULT 'unmatched',
    confidence           NUMERIC(5, 4),
    note                 TEXT NOT NULL DEFAULT '',
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_store_alias_identity
    ON store_aliases(source_name, normalized_store_name, city, mall_name, address);
CREATE INDEX IF NOT EXISTS idx_store_alias_status
    ON store_aliases(match_status, source_name);
CREATE INDEX IF NOT EXISTS idx_store_alias_store
    ON store_aliases(store_id);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id        VARCHAR(64) PRIMARY KEY,
    issue_key       VARCHAR(128) NOT NULL UNIQUE,
    entity_type     VARCHAR(64) NOT NULL,
    entity_key      VARCHAR(255) NOT NULL,
    source_name     VARCHAR(128) NOT NULL DEFAULT '',
    issue_type      VARCHAR(64) NOT NULL,
    severity        VARCHAR(16) NOT NULL
                    CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    status          VARCHAR(16) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'acknowledged', 'resolved', 'ignored')),
    message         TEXT NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP,
    resolution_note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_quality_issue_status
    ON data_quality_issues(status, severity, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_quality_issue_entity
    ON data_quality_issues(entity_type, entity_key);

CREATE TABLE IF NOT EXISTS data_quality_scan_runs (
    scan_id       VARCHAR(64) PRIMARY KEY,
    trigger_type  VARCHAR(32) NOT NULL,
    status        VARCHAR(16) NOT NULL
                  CHECK (status IN ('running', 'completed', 'failed')),
    issue_count   INT NOT NULL DEFAULT 0,
    summary       JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at   TIMESTAMP,
    error_message TEXT NOT NULL DEFAULT ''
);

ALTER TABLE data_source_logs
    ADD COLUMN IF NOT EXISTS run_id       VARCHAR(64),
    ADD COLUMN IF NOT EXISTS trace_id     VARCHAR(128),
    ADD COLUMN IF NOT EXISTS entity_id    VARCHAR(128),
    ADD COLUMN IF NOT EXISTS started_at   TIMESTAMP,
    ADD COLUMN IF NOT EXISTS finished_at  TIMESTAMP,
    ADD COLUMN IF NOT EXISTS metadata     JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_source_logs_run
    ON data_source_logs(run_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_logs_source_date
    ON data_source_logs(source_name, executed_at DESC);

GRANT ALL PRIVILEGES ON brand_aliases, store_aliases, data_quality_issues, data_quality_scan_runs TO brandpulse;

-- 只为现有明确主数据建立 confirmed 别名；不处理外部原始记录的品牌归属。
INSERT INTO brand_aliases (
    alias_id, brand_id, alias_text, normalized_alias, source_name, status, confidence, note
)
SELECT
    'seed_' || md5(brand_id || '|cn|' || brand_name_cn),
    brand_id,
    brand_name_cn,
    lower(regexp_replace(brand_name_cn, '[[:space:][:punct:]]+', '', 'g')),
    'brands',
    'confirmed',
    1.0000,
    '由 brands.brand_name_cn 初始化'
FROM brands
WHERE NULLIF(TRIM(brand_name_cn), '') IS NOT NULL
ON CONFLICT (brand_id, normalized_alias, source_name) DO NOTHING;

INSERT INTO brand_aliases (
    alias_id, brand_id, alias_text, normalized_alias, source_name, status, confidence, note
)
SELECT
    'seed_' || md5(brand_id || '|en|' || brand_name_en),
    brand_id,
    brand_name_en,
    lower(regexp_replace(brand_name_en, '[[:space:][:punct:]]+', '', 'g')),
    'brands',
    'confirmed',
    1.0000,
    '由 brands.brand_name_en 初始化'
FROM brands
WHERE NULLIF(TRIM(brand_name_en), '') IS NOT NULL
ON CONFLICT (brand_id, normalized_alias, source_name) DO NOTHING;

INSERT INTO brand_aliases (
    alias_id, brand_id, alias_text, normalized_alias, source_name, status, confidence, note
)
SELECT
    'seed_' || md5(brand_id || '|keyword|' || search_keywords),
    brand_id,
    search_keywords,
    lower(regexp_replace(search_keywords, '[[:space:][:punct:]]+', '', 'g')),
    'brands',
    'confirmed',
    0.9000,
    '由 brands.search_keywords 初始化'
FROM brands
WHERE NULLIF(TRIM(search_keywords), '') IS NOT NULL
ON CONFLICT (brand_id, normalized_alias, source_name) DO NOTHING;
