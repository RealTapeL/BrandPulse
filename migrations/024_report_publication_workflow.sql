-- 可追溯报告发布层。旧 report_runs 保留为队列与文件兼容记录；本表记录模板、快照、审核和分发。

CREATE TABLE IF NOT EXISTS report_templates (
    template_id           VARCHAR(64) PRIMARY KEY,
    template_version      VARCHAR(32) NOT NULL,
    display_name          VARCHAR(255) NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    definition            JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (template_id, template_version)
);

CREATE TABLE IF NOT EXISTS report_publications (
    publication_id        VARCHAR(64) PRIMARY KEY,
    report_id             VARCHAR(64) NOT NULL UNIQUE REFERENCES report_runs(report_id) ON DELETE CASCADE,
    snapshot_id           VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id),
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    template_id           VARCHAR(64) NOT NULL REFERENCES report_templates(template_id),
    template_version      VARCHAR(32) NOT NULL,
    status                VARCHAR(32) NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued', 'running', 'ready_for_review', 'approved', 'sent', 'failed', 'skipped')),
    audience              JSONB NOT NULL DEFAULT '[]'::jsonb,
    notification_channel  VARCHAR(32) NOT NULL DEFAULT 'download'
                          CHECK (notification_channel IN ('download', 'smtp', 'webhook')),
    data_cutoff_at        TIMESTAMP,
    source_coverage       JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_grade         VARCHAR(8) NOT NULL DEFAULT 'unrated',
    metric_version        VARCHAR(64) NOT NULL DEFAULT '',
    is_partial            BOOLEAN NOT NULL DEFAULT FALSE,
    watermark             TEXT NOT NULL DEFAULT '',
    requested_by          VARCHAR(64) NOT NULL DEFAULT 'system',
    approved_by           VARCHAR(64),
    approved_at           TIMESTAMP,
    approval_note         TEXT NOT NULL DEFAULT '',
    sent_at               TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_report_publications_scope_status
    ON report_publications(scope_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_publications_snapshot
    ON report_publications(snapshot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS report_review_events (
    review_event_id       VARCHAR(64) PRIMARY KEY,
    publication_id        VARCHAR(64) NOT NULL REFERENCES report_publications(publication_id) ON DELETE CASCADE,
    action                VARCHAR(24) NOT NULL CHECK (action IN ('submitted', 'approved', 'rejected', 'sent', 'downloaded')),
    actor_id              VARCHAR(64) NOT NULL DEFAULT 'system',
    note                  TEXT NOT NULL DEFAULT '',
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_report_review_events_publication
    ON report_review_events(publication_id, created_at DESC);

CREATE TABLE IF NOT EXISTS report_delivery_events (
    delivery_event_id     VARCHAR(64) PRIMARY KEY,
    publication_id        VARCHAR(64) NOT NULL REFERENCES report_publications(publication_id) ON DELETE CASCADE,
    channel               VARCHAR(32) NOT NULL CHECK (channel IN ('download', 'smtp', 'webhook')),
    recipient             VARCHAR(512) NOT NULL DEFAULT '',
    status                VARCHAR(24) NOT NULL CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    attempt_no            INT NOT NULL DEFAULT 1 CHECK (attempt_no >= 1),
    error_message         TEXT NOT NULL DEFAULT '',
    metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_report_delivery_events_publication
    ON report_delivery_events(publication_id, created_at DESC);

CREATE TABLE IF NOT EXISTS report_schedule_publication_configs (
    schedule_id           VARCHAR(64) PRIMARY KEY REFERENCES report_schedules(schedule_id) ON DELETE CASCADE,
    template_id           VARCHAR(64) NOT NULL REFERENCES report_templates(template_id),
    template_version      VARCHAR(32) NOT NULL,
    audience              JSONB NOT NULL DEFAULT '[]'::jsonb,
    notification_channel  VARCHAR(32) NOT NULL DEFAULT 'download'
                          CHECK (notification_channel IN ('download', 'smtp', 'webhook')),
    require_approval      BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by            VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO report_templates (template_id, template_version, display_name, description, definition)
VALUES (
    'trusted_snapshot_brief', 'v1', '可信快照简报',
    '以一个 ready/published 快照生成的可读摘要、数据质量说明和原始明细导出。',
    '{"sections":["summary","data_quality","opportunities","metric_evidence","raw_export"]}'::jsonb
)
ON CONFLICT (template_id) DO UPDATE SET
    template_version = EXCLUDED.template_version,
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    definition = EXCLUDED.definition,
    updated_at = CURRENT_TIMESTAMP;

GRANT ALL PRIVILEGES ON report_templates, report_publications, report_review_events,
    report_delivery_events, report_schedule_publication_configs TO brandpulse;
