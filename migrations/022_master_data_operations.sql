-- 主数据运营层：品牌/门店生命周期、原始观测映射决策、项目门店映射及可追溯回算请求。
-- 不修改历史 brands、stores、raw 表的结构或归属；所有确认动作都以新事实表保留历史。

-- 历史库已有一个同名关系简表（brand_id/related_brand_id），字段与可信主数据关系
-- 生命周期不同。新表使用 master_ 前缀，避免改写未纳管的历史表。
CREATE TABLE IF NOT EXISTS master_brand_relationships (
    relationship_id       VARCHAR(64) PRIMARY KEY,
    parent_brand_id       VARCHAR(32) NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    child_brand_id        VARCHAR(32) NOT NULL REFERENCES brands(brand_id) ON DELETE CASCADE,
    relationship_type     VARCHAR(32) NOT NULL
                          CHECK (relationship_type IN ('parent_subbrand', 'co_brand', 'regional_agent', 'affiliate', 'other')),
    effective_from        DATE,
    effective_to          DATE,
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                VARCHAR(24) NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'inactive', 'rejected')),
    confirmed_by          VARCHAR(64) NOT NULL DEFAULT 'system',
    confirmed_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (parent_brand_id, child_brand_id, relationship_type, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_master_brand_relationships_parent
    ON master_brand_relationships(parent_brand_id, status, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_master_brand_relationships_child
    ON master_brand_relationships(child_brand_id, status, effective_from DESC);

CREATE TABLE IF NOT EXISTS store_lifecycle_records (
    lifecycle_id          VARCHAR(64) PRIMARY KEY,
    store_id              VARCHAR(64) NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    status                VARCHAR(24) NOT NULL
                          CHECK (status IN ('preparing', 'operating', 'suspended', 'closed', 'relocated', 'unknown')),
    effective_from        DATE NOT NULL,
    effective_to          DATE,
    source_name           VARCHAR(128) NOT NULL DEFAULT 'manual',
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    note                  TEXT NOT NULL DEFAULT '',
    confirmed_by          VARCHAR(64) NOT NULL DEFAULT 'system',
    confirmed_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
    UNIQUE (store_id, status, effective_from)
);

CREATE INDEX IF NOT EXISTS idx_store_lifecycle_current
    ON store_lifecycle_records(store_id, effective_from DESC);

-- 每一次映射确认、拒绝和撤销均独立保存。is_current 只标识该观测当前生效的决策。
CREATE TABLE IF NOT EXISTS entity_mapping_decisions (
    mapping_id            VARCHAR(64) PRIMARY KEY,
    observation_id        VARCHAR(64) NOT NULL REFERENCES raw_observations(observation_id) ON DELETE CASCADE,
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    source_name           VARCHAR(128) NOT NULL,
    source_record_key     VARCHAR(512) NOT NULL,
    mapping_status        VARCHAR(24) NOT NULL
                          CHECK (mapping_status IN ('confirmed', 'rejected', 'revoked')),
    brand_id              VARCHAR(32) REFERENCES brands(brand_id) ON DELETE SET NULL,
    store_id              VARCHAR(64) REFERENCES stores(store_id) ON DELETE SET NULL,
    match_method          VARCHAR(32) NOT NULL
                          CHECK (match_method IN ('manual', 'exact_alias', 'imported', 'other')),
    confidence            NUMERIC(5, 4),
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_from        DATE,
    effective_to          DATE,
    is_current            BOOLEAN NOT NULL DEFAULT TRUE,
    supersedes_mapping_id VARCHAR(64) REFERENCES entity_mapping_decisions(mapping_id) ON DELETE SET NULL,
    reviewed_by           VARCHAR(64) NOT NULL,
    reviewed_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((mapping_status = 'confirmed' AND store_id IS NOT NULL AND brand_id IS NOT NULL)
           OR mapping_status IN ('rejected', 'revoked')),
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_mapping_current_observation
    ON entity_mapping_decisions(observation_id)
    WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_entity_mapping_scope_status
    ON entity_mapping_decisions(scope_id, mapping_status, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_entity_mapping_store
    ON entity_mapping_decisions(store_id, is_current);

-- 项目/范围与真实门店的显式关系，用于未来 POS、合同和客流等内部数据聚合。
-- 没有 confirmed 关系时，内部经营 API 必须返回“未完成映射”，而不是按旧 dataset key 猜测。
CREATE TABLE IF NOT EXISTS scope_store_mappings (
    scope_store_mapping_id VARCHAR(64) PRIMARY KEY,
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE CASCADE,
    store_id              VARCHAR(64) NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    mapping_status        VARCHAR(24) NOT NULL DEFAULT 'confirmed'
                          CHECK (mapping_status IN ('candidate', 'confirmed', 'excluded', 'revoked')),
    effective_from        DATE,
    effective_to          DATE,
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    confirmed_by          VARCHAR(64) NOT NULL DEFAULT 'system',
    confirmed_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from),
    UNIQUE (scope_id, store_id)
);

CREATE INDEX IF NOT EXISTS idx_scope_store_mapping_scope
    ON scope_store_mappings(scope_id, mapping_status, effective_from DESC);

-- 映射变更后可定位受影响快照；实际回算结果也在此留下台账。
CREATE TABLE IF NOT EXISTS mapping_recalculation_requests (
    request_id            VARCHAR(64) PRIMARY KEY,
    mapping_id            VARCHAR(64) REFERENCES entity_mapping_decisions(mapping_id) ON DELETE SET NULL,
    snapshot_id           VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    status                VARCHAR(24) NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    reason                VARCHAR(255) NOT NULL,
    requested_by          VARCHAR(64) NOT NULL,
    requested_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at            TIMESTAMP,
    finished_at           TIMESTAMP,
    error_message         TEXT NOT NULL DEFAULT '',
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (mapping_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_mapping_recalculation_snapshot
    ON mapping_recalculation_requests(snapshot_id, status, requested_at DESC);

GRANT ALL PRIVILEGES ON master_brand_relationships, store_lifecycle_records,
    entity_mapping_decisions, scope_store_mappings, mapping_recalculation_requests TO brandpulse;
