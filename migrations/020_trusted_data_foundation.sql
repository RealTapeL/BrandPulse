-- 可信品牌情报基础：在不改变历史表所有权和原始数据的前提下，新增可信数据层。
--
-- 早期核心表可能由部署账号 postgres 创建，而应用账号 brandpulse 只有 DML 权限。
-- 因此本迁移不 ALTER 这些历史表；通过新表和兼容关联表完成升级，避免生产迁移因
-- 表 owner 不一致而中断。历史表仍可供旧 API/路由读取，新正式链路只消费本迁移新增表。
--
-- 数据安全原则：
-- 1. 不删除或重写历史原始记录；
-- 2. 仅当 raw_record_lineage 能精确关联到旧 scope 时才分配到可信范围；
-- 3. 无法确认的历史记录写入 raw_observations，标识 legacy_unclassified；
-- 4. 不再把监测范围的数据集键当作 brands 中的真实品牌 ID。

-- 规范的城市×商场×品类范围。scope_id 复用一个已存在的规范 legacy scope ID，
-- 因此旧 crawl_schedules/report_runs 的外键无需重写；新范围则由应用同时创建兼容 scope。
CREATE TABLE IF NOT EXISTS trusted_monitoring_scopes (
    scope_id            VARCHAR(64) PRIMARY KEY,
    scope_key           VARCHAR(128) NOT NULL UNIQUE,
    city                VARCHAR(64) NOT NULL,
    mall_name           VARCHAR(255) NOT NULL,
    category            VARCHAR(64) NOT NULL,
    legacy_dataset_key  VARCHAR(128) NOT NULL DEFAULT '',
    status              VARCHAR(24) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'archived')),
    auto_publish        BOOLEAN NOT NULL DEFAULT FALSE,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'external_webbridge',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trusted_scopes_active
    ON trusted_monitoring_scopes(status, city, mall_name, category);

-- 旧 monitoring_scopes 只作为兼容登记；多个旧 scope 可指向同一个可信范围。
CREATE TABLE IF NOT EXISTS legacy_scope_links (
    legacy_scope_id     VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE CASCADE,
    legacy_dataset_key  VARCHAR(128) NOT NULL DEFAULT '',
    link_status         VARCHAR(24) NOT NULL
                        CHECK (link_status IN ('canonical', 'duplicate', 'unverified')),
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_legacy_scope_links_scope
    ON legacy_scope_links(scope_id, link_status);

-- 每个范围明确来源契约。当前可验证的公开来源是大众点评；小红书仍执行且保留状态，
-- 但未稳定接入时作为可选来源。单源快照会被明确标识，绝不将缺失来源按 0 补齐。
CREATE TABLE IF NOT EXISTS scope_source_requirements (
    requirement_id      VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE CASCADE,
    source_name         VARCHAR(128) NOT NULL,
    is_required         BOOLEAN NOT NULL DEFAULT TRUE,
    allow_empty         BOOLEAN NOT NULL DEFAULT FALSE,
    max_age_hours       INT NOT NULL DEFAULT 72 CHECK (max_age_hours BETWEEN 1 AND 8760),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scope_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_scope_source_requirements_scope
    ON scope_source_requirements(scope_id, is_active);

-- 一次采集编排，以及其中每个来源的真实执行结果。
CREATE TABLE IF NOT EXISTS collection_runs (
    collection_run_id   VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    crawl_job_id        VARCHAR(64),
    trigger_type        VARCHAR(24) NOT NULL DEFAULT 'manual'
                        CHECK (trigger_type IN ('manual', 'schedule', 'agent', 'cli', 'retry', 'migration')),
    status              VARCHAR(24) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'collecting', 'partial', 'completed', 'failed', 'cancelled')),
    expected_sources    JSONB NOT NULL DEFAULT '[]'::jsonb,
    requested_brand_id  VARCHAR(32),
    failure_reason      TEXT NOT NULL DEFAULT '',
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_scope_created
    ON collection_runs(scope_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_job
    ON collection_runs(crawl_job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_status
    ON collection_runs(status, created_at DESC);

CREATE TABLE IF NOT EXISTS source_runs (
    source_run_id       VARCHAR(64) PRIMARY KEY,
    collection_run_id   VARCHAR(64) NOT NULL REFERENCES collection_runs(collection_run_id) ON DELETE CASCADE,
    source_name         VARCHAR(128) NOT NULL,
    external_run_id     VARCHAR(128),
    source_log_id       VARCHAR(64),
    status              VARCHAR(24) NOT NULL DEFAULT 'collecting'
                        CHECK (status IN ('collecting', 'success', 'empty_validated', 'failed', 'skipped', 'stale')),
    record_count        INT NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    validated_count     INT NOT NULL DEFAULT 0 CHECK (validated_count >= 0),
    raw_saved_count     INT NOT NULL DEFAULT 0 CHECK (raw_saved_count >= 0),
    failure_reason      TEXT NOT NULL DEFAULT '',
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (collection_run_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_source_runs_collection
    ON source_runs(collection_run_id, source_name);
CREATE INDEX IF NOT EXISTS idx_source_runs_status
    ON source_runs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_runs_external
    ON source_runs(external_run_id)
    WHERE external_run_id IS NOT NULL;

-- 原始观测归属层。dp_shop_metrics/xhs_notes 继续保留，避免破坏旧查询和主键；
-- 只有这里的 scope_id 才是正式范围归属，brand_id 仅在 mapping confirmed 后写入。
CREATE TABLE IF NOT EXISTS raw_observations (
    observation_id          VARCHAR(64) PRIMARY KEY,
    scope_id                VARCHAR(64) REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE SET NULL,
    collection_run_id       VARCHAR(64) REFERENCES collection_runs(collection_run_id) ON DELETE SET NULL,
    source_run_id           VARCHAR(64) REFERENCES source_runs(source_run_id) ON DELETE SET NULL,
    source_name             VARCHAR(128) NOT NULL,
    record_type             VARCHAR(32) NOT NULL,
    source_record_key       VARCHAR(512) NOT NULL,
    source_url              VARCHAR(1024) NOT NULL DEFAULT '',
    legacy_dataset_key      VARCHAR(128) NOT NULL DEFAULT '',
    observed_date           DATE NOT NULL,
    captured_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_category            VARCHAR(128) NOT NULL DEFAULT '',
    standard_category       VARCHAR(128) NOT NULL DEFAULT '',
    category_mapping_status VARCHAR(24) NOT NULL DEFAULT 'pending'
                        CHECK (category_mapping_status IN ('confirmed', 'pending', 'rejected', 'legacy_unclassified')),
    candidate_brand_id      VARCHAR(32),
    brand_id                VARCHAR(32) REFERENCES brands(brand_id) ON DELETE SET NULL,
    store_id                VARCHAR(64) REFERENCES stores(store_id) ON DELETE SET NULL,
    entity_mapping_status   VARCHAR(24) NOT NULL DEFAULT 'pending'
                        CHECK (entity_mapping_status IN ('confirmed', 'pending', 'rejected', 'legacy_unclassified')),
    mapping_confidence      NUMERIC(5, 4),
    quality_status          VARCHAR(24) NOT NULL DEFAULT 'accepted'
                        CHECK (quality_status IN ('accepted', 'pending_review', 'rejected', 'legacy_unclassified')),
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_observations_identity
    ON raw_observations(source_name, record_type, source_record_key, observed_date, COALESCE(scope_id, ''));
CREATE INDEX IF NOT EXISTS idx_raw_observations_scope_date
    ON raw_observations(scope_id, observed_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_observations_source_run
    ON raw_observations(source_run_id, observed_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_observations_mapping
    ON raw_observations(entity_mapping_status, category_mapping_status, observed_date DESC);

-- 可发布快照。正式看板、报告、告警和后续指标默认只读 ready/published。
CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id            VARCHAR(64) PRIMARY KEY,
    scope_id               VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    collection_run_id      VARCHAR(64) NOT NULL UNIQUE REFERENCES collection_runs(collection_run_id),
    status                 VARCHAR(24) NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft', 'collecting', 'partial', 'validating', 'ready', 'published',
                                             'failed', 'rejected', 'expired', 'superseded')),
    expected_sources       JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_coverage        JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at            TIMESTAMP,
    captured_at            TIMESTAMP,
    freshness_status       VARCHAR(24) NOT NULL DEFAULT 'unknown'
                           CHECK (freshness_status IN ('fresh', 'stale', 'unknown')),
    quality_grade          VARCHAR(8) NOT NULL DEFAULT 'unrated'
                           CHECK (quality_grade IN ('A', 'B', 'C', 'D', 'F', 'unrated')),
    data_mode              VARCHAR(32) NOT NULL DEFAULT 'raw_only'
                           CHECK (data_mode IN ('multi_source', 'dianping_single_source', 'single_source', 'raw_only')),
    failure_reason         TEXT NOT NULL DEFAULT '',
    published_at           TIMESTAMP,
    supersedes_snapshot_id VARCHAR(64) REFERENCES data_snapshots(snapshot_id) ON DELETE SET NULL,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_data_snapshots_scope_status
    ON data_snapshots(scope_id, status, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_snapshots_published
    ON data_snapshots(status, published_at DESC)
    WHERE status IN ('ready', 'published');

CREATE TABLE IF NOT EXISTS snapshot_source_results (
    snapshot_source_result_id VARCHAR(64) PRIMARY KEY,
    snapshot_id               VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    source_run_id             VARCHAR(64) REFERENCES source_runs(source_run_id) ON DELETE SET NULL,
    source_name               VARCHAR(128) NOT NULL,
    is_required               BOOLEAN NOT NULL DEFAULT FALSE,
    status                    VARCHAR(24) NOT NULL
                              CHECK (status IN ('success', 'empty_validated', 'failed', 'skipped', 'stale')),
    record_count              INT NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    validated_count           INT NOT NULL DEFAULT 0 CHECK (validated_count >= 0),
    observed_at               TIMESTAMP,
    failure_reason            TEXT NOT NULL DEFAULT '',
    metadata                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_source_results_snapshot
    ON snapshot_source_results(snapshot_id, source_name);

-- 旧 report_runs 保持不变；新表提供报告与快照的一对一可追溯关联。
CREATE TABLE IF NOT EXISTS report_snapshot_links (
    report_id             VARCHAR(64) PRIMARY KEY,
    snapshot_id           VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id),
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(64) NOT NULL DEFAULT 'system'
);

-- 从已有范围中选取规范行：优先 MALL_* 采集数据集，否则选最早登记行。
WITH ranked AS (
    SELECT
        scope.scope_id AS legacy_scope_id,
        first_value(scope.scope_id) OVER (
            PARTITION BY scope.city, scope.mall_name, scope.category
            ORDER BY CASE WHEN scope.brand_id LIKE 'MALL_%' THEN 0 ELSE 1 END,
                     scope.created_at,
                     scope.scope_id
        ) AS canonical_scope_id,
        first_value(scope.brand_id) OVER (
            PARTITION BY scope.city, scope.mall_name, scope.category
            ORDER BY CASE WHEN scope.brand_id LIKE 'MALL_%' THEN 0 ELSE 1 END,
                     scope.created_at,
                     scope.scope_id
        ) AS canonical_dataset_key,
        'scopekey_' || md5(scope.city || '|' || scope.mall_name || '|' || scope.category) AS scope_key,
        scope.city,
        scope.mall_name,
        scope.category,
        scope.data_origin,
        row_number() OVER (
            PARTITION BY scope.city, scope.mall_name, scope.category
            ORDER BY CASE WHEN scope.brand_id LIKE 'MALL_%' THEN 0 ELSE 1 END,
                     scope.created_at,
                     scope.scope_id
        ) AS rank_no
    FROM monitoring_scopes AS scope
)
INSERT INTO trusted_monitoring_scopes (
    scope_id, scope_key, city, mall_name, category, legacy_dataset_key, status, data_origin
)
SELECT canonical_scope_id, scope_key, city, mall_name, category, canonical_dataset_key, 'active', data_origin
FROM ranked
WHERE rank_no = 1
ON CONFLICT (scope_id) DO NOTHING;

WITH ranked AS (
    SELECT
        scope.scope_id AS legacy_scope_id,
        scope.brand_id AS legacy_dataset_key,
        first_value(scope.scope_id) OVER (
            PARTITION BY scope.city, scope.mall_name, scope.category
            ORDER BY CASE WHEN scope.brand_id LIKE 'MALL_%' THEN 0 ELSE 1 END,
                     scope.created_at,
                     scope.scope_id
        ) AS canonical_scope_id
    FROM monitoring_scopes AS scope
)
INSERT INTO legacy_scope_links (
    legacy_scope_id, scope_id, legacy_dataset_key, link_status, evidence
)
SELECT
    ranked.legacy_scope_id,
    ranked.canonical_scope_id,
    ranked.legacy_dataset_key,
    CASE WHEN ranked.legacy_scope_id = ranked.canonical_scope_id THEN 'canonical' ELSE 'duplicate' END,
    jsonb_build_object('migration', '020_trusted_data_foundation', 'method', 'city_mall_category_exact')
FROM ranked
ON CONFLICT (legacy_scope_id) DO NOTHING;

INSERT INTO scope_source_requirements (
    requirement_id, scope_id, source_name, is_required, allow_empty, max_age_hours
)
SELECT
    'req_' || substr(md5(scope.scope_id || '|dianping_webbridge'), 1, 40),
    scope.scope_id,
    'dianping_webbridge',
    TRUE,
    FALSE,
    72
FROM trusted_monitoring_scopes AS scope
ON CONFLICT (scope_id, source_name) DO NOTHING;

INSERT INTO scope_source_requirements (
    requirement_id, scope_id, source_name, is_required, allow_empty, max_age_hours
)
SELECT
    'req_' || substr(md5(scope.scope_id || '|xiaohongshu_webbridge'), 1, 40),
    scope.scope_id,
    'xiaohongshu_webbridge',
    FALSE,
    TRUE,
    72
FROM trusted_monitoring_scopes AS scope
ON CONFLICT (scope_id, source_name) DO NOTHING;

-- 有明确旧 scope 的历史任务可被迁入 collection run；缺少 scope_id 的任务保持旧台账，绝不猜测。
INSERT INTO collection_runs (
    collection_run_id, scope_id, crawl_job_id, trigger_type, status,
    expected_sources, requested_brand_id, failure_reason, started_at, finished_at, created_at, updated_at
)
SELECT
    'collect_legacy_' || replace(job.job_id, '-', ''),
    link.scope_id,
    job.job_id,
    'migration',
    CASE job.status
        WHEN 'completed' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        WHEN 'running' THEN 'collecting'
        ELSE 'draft'
    END,
    COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'source_name', requirement.source_name,
            'required', requirement.is_required,
            'allow_empty', requirement.allow_empty,
            'max_age_hours', requirement.max_age_hours
        ) ORDER BY requirement.source_name)
        FROM scope_source_requirements AS requirement
        WHERE requirement.scope_id = link.scope_id AND requirement.is_active = TRUE
    ), '[]'::jsonb),
    CASE WHEN EXISTS (SELECT 1 FROM brands WHERE brand_id = job.brand_id) THEN job.brand_id ELSE NULL END,
    CASE WHEN job.status = 'failed' THEN COALESCE(job.result, '') ELSE '' END,
    job.started_at,
    job.finished_at,
    COALESCE(job.created_at, CURRENT_TIMESTAMP),
    COALESCE(job.updated_at, CURRENT_TIMESTAMP)
FROM crawl_jobs AS job
JOIN legacy_scope_links AS link ON link.legacy_scope_id = job.scope_id
ON CONFLICT (collection_run_id) DO NOTHING;

INSERT INTO source_runs (
    source_run_id, collection_run_id, source_name, external_run_id, source_log_id,
    status, record_count, validated_count, raw_saved_count, failure_reason,
    metadata, started_at, finished_at, created_at, updated_at
)
SELECT
    'source_legacy_' || substr(md5(log.log_id), 1, 40),
    collection.collection_run_id,
    log.source_name,
    log.run_id,
    log.log_id,
    CASE
        WHEN lower(COALESCE(log.status, '')) IN ('completed', 'success') AND COALESCE(log.record_count, 0) > 0 THEN 'success'
        WHEN lower(COALESCE(log.status, '')) IN ('empty', 'empty_validated') THEN 'empty_validated'
        WHEN lower(COALESCE(log.status, '')) IN ('failed', 'error') THEN 'failed'
        ELSE 'skipped'
    END,
    GREATEST(COALESCE(log.record_count, 0), 0),
    GREATEST(COALESCE(log.record_count, 0), 0),
    GREATEST(COALESCE((log.metadata ->> 'raw_saved')::int, 0), 0),
    COALESCE(log.error_message, ''),
    COALESCE(log.metadata, '{}'::jsonb),
    log.started_at,
    log.finished_at,
    COALESCE(log.executed_at, CURRENT_TIMESTAMP),
    COALESCE(log.finished_at, log.executed_at, CURRENT_TIMESTAMP)
FROM data_source_logs AS log
JOIN collection_runs AS collection ON collection.crawl_job_id = log.trace_id
ON CONFLICT (collection_run_id, source_name) DO NOTHING;

-- 已有血缘可精确验证的点评记录进入规范 scope；未关联血缘的记录保留为 legacy_unclassified。
INSERT INTO raw_observations (
    observation_id, scope_id, collection_run_id, source_run_id,
    source_name, record_type, source_record_key, source_url, legacy_dataset_key,
    observed_date, raw_category, standard_category, category_mapping_status,
    candidate_brand_id, entity_mapping_status, quality_status, payload, created_at, updated_at
)
SELECT
    'rawobs_dp_' || substr(md5(dp.shop_name || '|' || dp.city || '|' || dp.crawl_date || '|' || dp.brand_id || '|' || dp.place), 1, 40),
    link.scope_id,
    collection.collection_run_id,
    source_run.source_run_id,
    'dianping_webbridge',
    'dp_shop_metric',
    COALESCE(lineage.record_key, md5(dp.shop_name || '|' || dp.city || '|' || dp.crawl_date || '|' || dp.brand_id || '|' || dp.place)),
    COALESCE(dp.source_url, ''),
    dp.brand_id,
    dp.crawl_date,
    COALESCE(scope.category, ''),
    COALESCE(scope.category, 'legacy_unclassified'),
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'confirmed' END,
    CASE WHEN EXISTS (SELECT 1 FROM brands WHERE brand_id = dp.brand_id) THEN dp.brand_id ELSE NULL END,
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'pending' END,
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'accepted' END,
    jsonb_build_object(
        'shop_name', dp.shop_name, 'city', dp.city, 'place', dp.place,
        'score', dp.score, 'review_count', dp.review_count, 'avg_price', dp.avg_price,
        'business_area', dp.business_area, 'shop_text', dp.shop_text, 'source_url', dp.source_url
    ),
    COALESCE(dp.created_at, CURRENT_TIMESTAMP),
    CURRENT_TIMESTAMP
FROM dp_shop_metrics AS dp
LEFT JOIN LATERAL (
    SELECT line.*
    FROM raw_record_lineage AS line
    WHERE line.record_type = 'dp_shop_metric'
      AND line.source_name = 'dianping_webbridge'
      AND line.crawl_date = dp.crawl_date
      AND line.metadata ->> 'brand_id' = dp.brand_id
      AND line.metadata ->> 'city' = dp.city
      AND COALESCE(line.metadata ->> 'place', '') = COALESCE(dp.place, '')
      AND line.metadata ->> 'shop_name' = dp.shop_name
    ORDER BY line.created_at DESC
    LIMIT 1
) AS lineage ON TRUE
LEFT JOIN legacy_scope_links AS link ON link.legacy_scope_id = lineage.scope_id
LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = link.scope_id
LEFT JOIN collection_runs AS collection ON collection.crawl_job_id = lineage.crawl_job_id
LEFT JOIN source_runs AS source_run
  ON source_run.collection_run_id = collection.collection_run_id
 AND source_run.source_name = 'dianping_webbridge'
ON CONFLICT DO NOTHING;

INSERT INTO raw_observations (
    observation_id, scope_id, collection_run_id, source_run_id,
    source_name, record_type, source_record_key, source_url, legacy_dataset_key,
    observed_date, raw_category, standard_category, category_mapping_status,
    candidate_brand_id, entity_mapping_status, quality_status, payload, created_at, updated_at
)
SELECT
    'rawobs_xhs_' || substr(md5(note.note_id || '|' || note.crawl_date || '|' || COALESCE(link.scope_id, '')), 1, 40),
    link.scope_id,
    collection.collection_run_id,
    source_run.source_run_id,
    'xiaohongshu_webbridge',
    'xhs_note',
    note.note_id,
    COALESCE(note.note_url, ''),
    note.brand_id,
    note.crawl_date,
    COALESCE(scope.category, ''),
    COALESCE(scope.category, 'legacy_unclassified'),
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'confirmed' END,
    CASE WHEN EXISTS (SELECT 1 FROM brands WHERE brand_id = note.brand_id) THEN note.brand_id ELSE NULL END,
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'pending' END,
    CASE WHEN link.scope_id IS NULL THEN 'legacy_unclassified' ELSE 'accepted' END,
    jsonb_build_object(
        'note_id', note.note_id, 'title', note.title, 'author_name', note.author_name,
        'likes', note.likes, 'publish_time', note.publish_time, 'city', note.city,
        'mall_name', note.mall_name, 'keyword', note.keyword, 'note_url', note.note_url
    ),
    COALESCE(note.created_at, CURRENT_TIMESTAMP),
    CURRENT_TIMESTAMP
FROM xhs_notes AS note
LEFT JOIN LATERAL (
    SELECT line.*
    FROM raw_record_lineage AS line
    WHERE line.record_type = 'xhs_note'
      AND line.source_name = 'xiaohongshu_webbridge'
      AND line.record_key = note.note_id
    ORDER BY line.created_at DESC
    LIMIT 1
) AS lineage ON TRUE
LEFT JOIN legacy_scope_links AS link ON link.legacy_scope_id = lineage.scope_id
LEFT JOIN trusted_monitoring_scopes AS scope ON scope.scope_id = link.scope_id
LEFT JOIN collection_runs AS collection ON collection.crawl_job_id = lineage.crawl_job_id
LEFT JOIN source_runs AS source_run
  ON source_run.collection_run_id = collection.collection_run_id
 AND source_run.source_name = 'xiaohongshu_webbridge'
ON CONFLICT DO NOTHING;

-- 仅来源记录和原始保存都可验证的历史任务获得 ready 快照；没有可验证数据的任务不假装完整。
INSERT INTO data_snapshots (
    snapshot_id, scope_id, collection_run_id, status, expected_sources, source_coverage,
    observed_at, captured_at, freshness_status, quality_grade, data_mode,
    failure_reason, created_at, updated_at
)
SELECT
    'snapshot_legacy_' || substr(md5(run.collection_run_id), 1, 40),
    run.scope_id,
    run.collection_run_id,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM source_runs AS source
            WHERE source.collection_run_id = run.collection_run_id
              AND source.source_name = 'dianping_webbridge'
              AND source.status = 'success'
              AND source.raw_saved_count > 0
        ) THEN 'ready'
        WHEN run.status = 'failed' THEN 'failed'
        ELSE 'partial'
    END,
    run.expected_sources,
    jsonb_build_object(
        'expected_count', jsonb_array_length(run.expected_sources),
        'executed_count', (SELECT COUNT(*) FROM source_runs source WHERE source.collection_run_id = run.collection_run_id),
        'success_count', (SELECT COUNT(*) FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.status = 'success'),
        'empty_validated_count', (SELECT COUNT(*) FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.status = 'empty_validated'),
        'failed_count', (SELECT COUNT(*) FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.status = 'failed')
    ),
    COALESCE(run.finished_at, run.started_at, run.created_at),
    COALESCE(run.finished_at, run.started_at, run.created_at),
    CASE WHEN COALESCE(run.finished_at, run.started_at, run.created_at) >= CURRENT_TIMESTAMP - INTERVAL '72 hours' THEN 'fresh' ELSE 'stale' END,
    CASE
        WHEN EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'dianping_webbridge' AND source.status = 'success')
         AND EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'xiaohongshu_webbridge' AND source.status = 'success') THEN 'A'
        WHEN EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'dianping_webbridge' AND source.status = 'success') THEN 'B'
        WHEN run.status = 'failed' THEN 'F'
        ELSE 'C'
    END,
    CASE
        WHEN EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'dianping_webbridge' AND source.status = 'success')
         AND EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'xiaohongshu_webbridge' AND source.status = 'success') THEN 'multi_source'
        WHEN EXISTS (SELECT 1 FROM source_runs source WHERE source.collection_run_id = run.collection_run_id AND source.source_name = 'dianping_webbridge' AND source.status = 'success') THEN 'dianping_single_source'
        ELSE 'raw_only'
    END,
    CASE WHEN run.status = 'failed' THEN run.failure_reason ELSE '' END,
    run.created_at,
    CURRENT_TIMESTAMP
FROM collection_runs AS run
ON CONFLICT (collection_run_id) DO NOTHING;

INSERT INTO snapshot_source_results (
    snapshot_source_result_id, snapshot_id, source_run_id, source_name, is_required,
    status, record_count, validated_count, observed_at, failure_reason, metadata, created_at, updated_at
)
SELECT
    'snapshot_source_' || substr(md5(snapshot.snapshot_id || '|' || source.source_name), 1, 36),
    snapshot.snapshot_id,
    source.source_run_id,
    source.source_name,
    COALESCE(requirement.is_required, FALSE),
    source.status,
    source.record_count,
    source.validated_count,
    COALESCE(source.finished_at, source.created_at),
    source.failure_reason,
    source.metadata,
    source.created_at,
    CURRENT_TIMESTAMP
FROM data_snapshots AS snapshot
JOIN source_runs AS source ON source.collection_run_id = snapshot.collection_run_id
LEFT JOIN scope_source_requirements AS requirement
  ON requirement.scope_id = snapshot.scope_id
 AND requirement.source_name = source.source_name
ON CONFLICT (snapshot_id, source_name) DO NOTHING;

GRANT ALL PRIVILEGES ON trusted_monitoring_scopes, legacy_scope_links,
    scope_source_requirements, collection_runs, source_runs, raw_observations,
    data_snapshots, snapshot_source_results, report_snapshot_links TO brandpulse;
