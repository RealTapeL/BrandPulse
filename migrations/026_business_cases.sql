-- 可处理业务事项：把告警、数据质量、采集失败和机会信号转为可分派、可反馈的闭环。

CREATE TABLE IF NOT EXISTS business_cases (
    case_id                    VARCHAR(64) PRIMARY KEY,
    scope_id                   VARCHAR(64) REFERENCES trusted_monitoring_scopes(scope_id),
    case_type                  VARCHAR(32) NOT NULL CHECK (case_type IN (
                                'data_quality', 'collection_exception', 'brand_risk',
                                'operations_risk', 'opportunity', 'manual')),
    source_type                VARCHAR(32) NOT NULL CHECK (source_type IN (
                                'alert_history', 'opportunity_signal', 'data_quality_issue',
                                'collection_run', 'source_run', 'report_publication', 'brand', 'store', 'manual')),
    source_id                  VARCHAR(128) NOT NULL,
    title                      VARCHAR(255) NOT NULL,
    description                TEXT NOT NULL DEFAULT '',
    priority                   VARCHAR(16) NOT NULL DEFAULT 'normal'
                                CHECK (priority IN ('critical', 'high', 'normal', 'low')),
    status                     VARCHAR(32) NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open', 'acknowledged', 'investigating',
                                    'action_planned', 'in_progress', 'resolved', 'closed')),
    owner_id                   VARCHAR(64),
    due_at                     TIMESTAMP,
    evidence                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_links             JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome                    TEXT NOT NULL DEFAULT '',
    feedback                   VARCHAR(32) NOT NULL DEFAULT 'pending'
                                CHECK (feedback IN ('pending', 'valid', 'false_positive',
                                    'no_action_required', 'data_problem')),
    rule_adjustment_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    closed_by                  VARCHAR(64),
    closed_at                  TIMESTAMP,
    created_by                 VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_business_cases_scope_status
    ON business_cases(scope_id, status, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_business_cases_source
    ON business_cases(source_type, source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_business_cases_owner_status
    ON business_cases(owner_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS business_case_events (
    event_id                   VARCHAR(64) PRIMARY KEY,
    case_id                    VARCHAR(64) NOT NULL REFERENCES business_cases(case_id) ON DELETE CASCADE,
    action                     VARCHAR(32) NOT NULL CHECK (action IN (
                                'created', 'commented', 'assigned', 'status_changed',
                                'feedback_recorded', 'closed', 'reopened')),
    actor_id                   VARCHAR(64) NOT NULL DEFAULT 'system',
    note                       TEXT NOT NULL DEFAULT '',
    payload                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_business_case_events_case
    ON business_case_events(case_id, created_at DESC);

GRANT ALL PRIVILEGES ON business_cases, business_case_events TO brandpulse;
