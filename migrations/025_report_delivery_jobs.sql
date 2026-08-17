-- 报告分发执行队列。report_delivery_events 保留为不可变投递台账；本表负责可靠重试。
-- 独立新表避免修改历史 report_runs / report_delivery_events 结构。

CREATE TABLE IF NOT EXISTS report_delivery_jobs (
    delivery_job_id       VARCHAR(64) PRIMARY KEY,
    publication_id        VARCHAR(64) NOT NULL REFERENCES report_publications(publication_id) ON DELETE CASCADE,
    channel               VARCHAR(32) NOT NULL CHECK (channel IN ('smtp', 'webhook')),
    recipient             VARCHAR(512) NOT NULL,
    status                VARCHAR(24) NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'sending', 'retry', 'sent', 'failed', 'cancelled')),
    attempt_count         INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts          INT NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 10),
    next_attempt_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error            TEXT NOT NULL DEFAULT '',
    response              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at               TIMESTAMP,
    UNIQUE (publication_id, channel, recipient)
);

CREATE INDEX IF NOT EXISTS idx_report_delivery_jobs_due
    ON report_delivery_jobs(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_report_delivery_jobs_publication
    ON report_delivery_jobs(publication_id, created_at DESC);

GRANT ALL PRIVILEGES ON report_delivery_jobs TO brandpulse;
