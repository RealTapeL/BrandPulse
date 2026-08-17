-- 自定义公式的正式计算结果必须绑定 scope 和 snapshot；旧 custom_formula_values 仅保留历史兼容读取。

CREATE TABLE IF NOT EXISTS snapshot_formula_evaluations (
    evaluation_id       VARCHAR(64) PRIMARY KEY,
    formula_id          VARCHAR(36) NOT NULL REFERENCES custom_formulas(formula_id) ON DELETE CASCADE,
    scope_id            VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    snapshot_id         VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    status              VARCHAR(16) NOT NULL CHECK (status IN ('completed', 'skipped', 'failed')),
    value               NUMERIC(20, 6),
    input_metrics       JSONB NOT NULL DEFAULT '{}'::jsonb,
    formula_definition  JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason      TEXT NOT NULL DEFAULT '',
    evaluated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formula_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_formula_evaluations_scope_snapshot
    ON snapshot_formula_evaluations(scope_id, snapshot_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_formula_evaluations_formula
    ON snapshot_formula_evaluations(formula_id, evaluated_at DESC);

GRANT ALL PRIVILEGES ON snapshot_formula_evaluations TO brandpulse;
