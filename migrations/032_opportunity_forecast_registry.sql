-- Phase 5～8：机会规则扩展、预测准入和模型发布台账。
-- 只增加约束/台账，不删除历史机会、训练运行或模型工件。

ALTER TABLE opportunity_signals
    DROP CONSTRAINT IF EXISTS opportunity_signals_signal_type_check;

ALTER TABLE opportunity_signals
    ADD CONSTRAINT opportunity_signals_signal_type_check CHECK (
        signal_type IN (
            'high_reputation_low_review_share',
            'high_visibility_low_reputation',
            'recent_growth',
            'continuous_decline',
            'competitor_present_missing',
            'category_gap',
            'insufficient_data',
            'source_anomaly',
            'data_mapping_incomplete',
            'source_coverage_incomplete',
            'trend_requires_validation'
        )
    );

ALTER TABLE opportunity_signals
    ADD COLUMN IF NOT EXISTS rule_version VARCHAR(32) NOT NULL DEFAULT 'opportunity-v1',
    ADD COLUMN IF NOT EXISTS information_gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence_status VARCHAR(24) NOT NULL DEFAULT 'available'
        CHECK (evidence_status IN ('available', 'partial', 'insufficient', 'stale', 'invalid')),
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(64);

CREATE TABLE IF NOT EXISTS opportunity_signal_events (
    event_id       VARCHAR(80) PRIMARY KEY,
    signal_id      VARCHAR(64) NOT NULL REFERENCES opportunity_signals(signal_id) ON DELETE CASCADE,
    from_status    VARCHAR(32) NOT NULL DEFAULT '',
    to_status      VARCHAR(32) NOT NULL,
    actor_id       VARCHAR(64) NOT NULL DEFAULT 'system',
    actor_role     VARCHAR(32) NOT NULL DEFAULT '',
    comment        TEXT NOT NULL DEFAULT '',
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_opportunity_signal_events_signal
    ON opportunity_signal_events(signal_id, created_at DESC);

CREATE TABLE IF NOT EXISTS forecast_readiness_checks (
    check_id             VARCHAR(80) PRIMARY KEY,
    scope_id             VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    target_metric        VARCHAR(128) NOT NULL,
    entity_type          VARCHAR(32) NOT NULL,
    status               VARCHAR(24) NOT NULL
                         CHECK (status IN ('ready', 'not_ready', 'blocked', 'error')),
    eligible_periods     INT NOT NULL DEFAULT 0 CHECK (eligible_periods >= 0),
    required_periods     INT NOT NULL DEFAULT 12 CHECK (required_periods >= 1),
    source_coverage      NUMERIC(8, 6),
    mapping_stability    NUMERIC(8, 6),
    latest_snapshot_id   VARCHAR(64) REFERENCES data_snapshots(snapshot_id) ON DELETE SET NULL,
    missing_periods      JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers             JSONB NOT NULL DEFAULT '[]'::jsonb,
    details              JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_forecast_readiness_scope_metric
    ON forecast_readiness_checks(scope_id, target_metric, entity_type, checked_at DESC);

CREATE TABLE IF NOT EXISTS model_registry (
    model_version_id     VARCHAR(80) PRIMARY KEY,
    model_id             VARCHAR(128) NOT NULL,
    run_id               VARCHAR(64) REFERENCES ml_training_runs(run_id) ON DELETE SET NULL,
    scope_id             VARCHAR(64) REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE SET NULL,
    target_metric        VARCHAR(128) NOT NULL,
    entity_type          VARCHAR(32) NOT NULL,
    task                 VARCHAR(64) NOT NULL,
    model_family         VARCHAR(64) NOT NULL,
    status               VARCHAR(32) NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'trained', 'evaluated', 'pending_approval',
                                           'published', 'monitoring', 'degraded', 'retired', 'archived')),
    data_origin          VARCHAR(64) NOT NULL DEFAULT 'public_benchmark',
    production_eligible  BOOLEAN NOT NULL DEFAULT FALSE,
    feature_version      VARCHAR(64) NOT NULL DEFAULT '',
    input_snapshot_id    VARCHAR(64) REFERENCES data_snapshots(snapshot_id) ON DELETE SET NULL,
    artifact_path        TEXT NOT NULL DEFAULT '',
    artifact_sha256      VARCHAR(64) NOT NULL DEFAULT '',
    metrics              JSONB NOT NULL DEFAULT '{}'::jsonb,
    baseline_metrics     JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by           VARCHAR(64) NOT NULL DEFAULT 'system',
    approved_by          VARCHAR(64),
    approved_at          TIMESTAMP,
    published_at         TIMESTAMP,
    retired_at           TIMESTAMP,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_id)
);

CREATE INDEX IF NOT EXISTS idx_model_registry_scope_target
    ON model_registry(scope_id, target_metric, entity_type, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS model_routes (
    route_id             VARCHAR(80) PRIMARY KEY,
    scope_id             VARCHAR(64) REFERENCES trusted_monitoring_scopes(scope_id) ON DELETE CASCADE,
    target_metric        VARCHAR(128) NOT NULL,
    entity_type          VARCHAR(32) NOT NULL,
    model_version_id     VARCHAR(80) NOT NULL REFERENCES model_registry(model_version_id),
    status               VARCHAR(24) NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'disabled')),
    created_by           VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scope_id, target_metric, entity_type)
);

CREATE TABLE IF NOT EXISTS forecast_results (
    forecast_id          VARCHAR(80) PRIMARY KEY,
    model_version_id     VARCHAR(80) NOT NULL REFERENCES model_registry(model_version_id),
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    input_snapshot_id     VARCHAR(64) REFERENCES data_snapshots(snapshot_id) ON DELETE SET NULL,
    target_metric         VARCHAR(128) NOT NULL,
    entity_type           VARCHAR(32) NOT NULL,
    entity_key            VARCHAR(512) NOT NULL,
    forecast_date         DATE NOT NULL,
    point_forecast        NUMERIC,
    lower_bound           NUMERIC,
    upper_bound           NUMERIC,
    actual_value          NUMERIC,
    status                VARCHAR(24) NOT NULL DEFAULT 'forecasted'
                          CHECK (status IN ('forecasted', 'observed', 'invalidated')),
    quality               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_version_id, entity_type, entity_key, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_forecast_results_scope_date
    ON forecast_results(scope_id, target_metric, forecast_date DESC);

GRANT ALL PRIVILEGES ON opportunity_signal_events TO brandpulse;
GRANT ALL PRIVILEGES ON forecast_readiness_checks TO brandpulse;
GRANT ALL PRIVILEGES ON model_registry TO brandpulse;
GRANT ALL PRIVILEGES ON model_routes TO brandpulse;
GRANT ALL PRIVILEGES ON forecast_results TO brandpulse;
