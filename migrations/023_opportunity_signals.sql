-- 招商机会信号：基于单一可信快照、明确指标和质量等级形成“待核实线索”，不等同于招商结论。

CREATE TABLE IF NOT EXISTS opportunity_signals (
    signal_id             VARCHAR(64) PRIMARY KEY,
    snapshot_id           VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    scope_id              VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    brand_id              VARCHAR(32) REFERENCES brands(brand_id) ON DELETE SET NULL,
    store_id              VARCHAR(64) REFERENCES stores(store_id) ON DELETE SET NULL,
    entity_type           VARCHAR(32) NOT NULL
                          CHECK (entity_type IN ('scope', 'brand', 'store', 'observation')),
    entity_key            VARCHAR(512) NOT NULL,
    entity_name           VARCHAR(255) NOT NULL,
    signal_type           VARCHAR(64) NOT NULL
                          CHECK (signal_type IN (
                              'high_reputation_low_review_share',
                              'data_mapping_incomplete',
                              'source_coverage_incomplete',
                              'trend_requires_validation'
                          )),
    signal_class          VARCHAR(24) NOT NULL
                          CHECK (signal_class IN ('opportunity', 'risk', 'data_quality', 'information')),
    trigger_rule          TEXT NOT NULL,
    metric_evidence       JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_evidence       JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_grade         VARCHAR(8) NOT NULL DEFAULT 'unrated',
    confidence            NUMERIC(5, 4),
    recommended_action    TEXT NOT NULL DEFAULT '',
    lifecycle_status      VARCHAR(32) NOT NULL DEFAULT 'discovered'
                          CHECK (lifecycle_status IN (
                              'discovered', 'master_confirmed', 'profile_incomplete', 'under_review',
                              'qualified', 'outreach', 'negotiation', 'introduced', 'rejected', 'archived'
                          )),
    human_confirmed       BOOLEAN NOT NULL DEFAULT FALSE,
    owner_id              VARCHAR(64),
    human_comment         TEXT NOT NULL DEFAULT '',
    resolved_at           TIMESTAMP,
    generated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, signal_type, entity_type, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_opportunity_signals_scope_snapshot
    ON opportunity_signals(scope_id, snapshot_id, signal_class, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_signals_lifecycle
    ON opportunity_signals(lifecycle_status, owner_id, updated_at DESC);

GRANT ALL PRIVILEGES ON opportunity_signals TO brandpulse;
