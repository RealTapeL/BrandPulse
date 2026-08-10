-- 项目/品类监测范围、自动采集计划与可追溯报告。
-- 所有计划默认关闭；没有真实采集数据时不得生成正式报告。

CREATE TABLE IF NOT EXISTS monitoring_scopes (
    scope_id            VARCHAR(64) PRIMARY KEY,
    brand_id            VARCHAR(32) NOT NULL,
    city                VARCHAR(64) NOT NULL,
    mall_name           VARCHAR(255) NOT NULL,
    category            VARCHAR(64) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'external_webbridge',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (brand_id, city, mall_name, category)
);

CREATE INDEX IF NOT EXISTS idx_monitoring_scopes_active
    ON monitoring_scopes(is_active, city, mall_name, category);

-- 从历史采集任务回填可选项目/品类范围；不会凭空创建业务数据。
INSERT INTO monitoring_scopes (
    scope_id, brand_id, city, mall_name, category, data_origin
)
SELECT DISTINCT
    'scope_' || substr(md5(job.brand_id || '|' || city_item.city || '|' || job.mall || '|' || job.category), 1, 24),
    job.brand_id,
    city_item.city,
    job.mall,
    job.category,
    'historical_crawl_job'
FROM crawl_jobs AS job
CROSS JOIN LATERAL unnest(COALESCE(job.cities, ARRAY[]::text[])) AS city_item(city)
WHERE COALESCE(job.brand_id, '') <> ''
  AND COALESCE(city_item.city, '') <> ''
  AND COALESCE(job.mall, '') <> ''
  AND COALESCE(job.category, '') <> ''
ON CONFLICT (brand_id, city, mall_name, category) DO NOTHING;

-- 早期 CLI 商场采集以 MALL_<hash> 作为数据集 ID；仅当哈希可由历史项目、城市、品类
-- 精确复算时才回填范围，避免把不同品类的历史数据混在同一个项目下。
INSERT INTO monitoring_scopes (
    scope_id, brand_id, city, mall_name, category, data_origin
)
SELECT DISTINCT
    'scope_' || substr(md5(raw.brand_id || '|' || raw.city || '|' || raw.mall_name || '|' || job.category), 1, 24),
    raw.brand_id,
    raw.city,
    raw.mall_name,
    job.category,
    'historical_hash_verified'
FROM (
    SELECT DISTINCT brand_id, city, place AS mall_name
    FROM dp_shop_metrics
    WHERE COALESCE(place, '') <> ''
) AS raw
JOIN crawl_jobs AS job
  ON raw.city = ANY(COALESCE(job.cities, ARRAY[]::text[]))
 AND raw.mall_name = job.mall
 AND raw.brand_id = 'MALL_' || substr(md5(raw.city || '|' || raw.mall_name || '|' || job.category), 1, 8)
ON CONFLICT (brand_id, city, mall_name, category) DO NOTHING;

ALTER TABLE crawl_jobs
    ADD COLUMN IF NOT EXISTS scope_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS schedule_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(16) NOT NULL DEFAULT 'manual';

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_scope_created
    ON crawl_jobs(scope_id, created_at DESC);

CREATE TABLE IF NOT EXISTS crawl_schedules (
    schedule_id         VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES monitoring_scopes(scope_id),
    interval_minutes    INT NOT NULL CHECK (interval_minutes BETWEEN 30 AND 10080),
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    max_attempts        INT NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 5),
    last_enqueued_at    TIMESTAMP,
    last_success_at     TIMESTAMP,
    last_error          TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crawl_schedules_due
    ON crawl_schedules(enabled, last_enqueued_at);

CREATE TABLE IF NOT EXISTS report_runs (
    report_id           VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES monitoring_scopes(scope_id),
    schedule_id         VARCHAR(64),
    trigger_type        VARCHAR(16) NOT NULL DEFAULT 'manual',
    report_type         VARCHAR(16) NOT NULL DEFAULT 'snapshot',
    file_format         VARCHAR(16) NOT NULL CHECK (file_format IN ('csv', 'xlsx')),
    status              VARCHAR(16) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped')),
    rq_job_id           VARCHAR(128),
    snapshot_date       DATE,
    file_path           TEXT,
    row_count           BIGINT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_report_runs_scope_created
    ON report_runs(scope_id, created_at DESC);

CREATE TABLE IF NOT EXISTS report_schedules (
    schedule_id         VARCHAR(64) PRIMARY KEY,
    scope_id            VARCHAR(64) NOT NULL REFERENCES monitoring_scopes(scope_id),
    frequency           VARCHAR(16) NOT NULL CHECK (frequency IN ('daily', 'weekly')),
    hour                INT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    minute              INT NOT NULL CHECK (minute BETWEEN 0 AND 59),
    weekday             INT CHECK (weekday BETWEEN 0 AND 6),
    file_format         VARCHAR(16) NOT NULL DEFAULT 'xlsx' CHECK (file_format IN ('csv', 'xlsx')),
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    last_enqueued_for   DATE,
    last_error          TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((frequency = 'daily' AND weekday IS NULL) OR (frequency = 'weekly' AND weekday IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_report_schedules_due
    ON report_schedules(enabled, frequency, hour, minute);

GRANT ALL PRIVILEGES ON monitoring_scopes, crawl_schedules, report_runs, report_schedules TO brandpulse;
