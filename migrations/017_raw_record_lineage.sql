-- 原始记录级采集血缘：不修改历史原始表，由独立映射表关联来源批次与任务。

CREATE TABLE IF NOT EXISTS raw_record_lineage (
    lineage_id    VARCHAR(64) PRIMARY KEY,
    run_id        VARCHAR(64) NOT NULL,
    crawl_job_id  VARCHAR(36) REFERENCES crawl_jobs(job_id) ON DELETE SET NULL,
    scope_id      VARCHAR(64) REFERENCES monitoring_scopes(scope_id) ON DELETE SET NULL,
    source_name   VARCHAR(128) NOT NULL,
    record_type   VARCHAR(32) NOT NULL,
    record_key    VARCHAR(256) NOT NULL,
    crawl_date    DATE NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, record_type, record_key)
);

CREATE INDEX IF NOT EXISTS idx_raw_lineage_job
    ON raw_record_lineage(crawl_job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_lineage_run
    ON raw_record_lineage(run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_lineage_record
    ON raw_record_lineage(record_type, record_key, created_at DESC);

GRANT ALL PRIVILEGES ON raw_record_lineage TO brandpulse;
