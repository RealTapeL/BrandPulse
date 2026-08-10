-- 机器学习训练运行台账。
-- 公开基准训练必须标注 data_origin，production_eligible 默认 false，
-- 避免把公开数据的模型结果误当成内部经营模型。
CREATE TABLE IF NOT EXISTS ml_training_runs (
    run_id              VARCHAR(64) PRIMARY KEY,
    task                VARCHAR(64) NOT NULL,
    dataset_key         VARCHAR(128) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'success', 'failed')),
    rq_job_id           VARCHAR(128),
    parameters          JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics             JSONB,
    artifact_path       TEXT,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'public_benchmark',
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    train_rows          BIGINT,
    validation_rows     BIGINT,
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_training_runs_created
    ON ml_training_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_training_runs_dataset
    ON ml_training_runs(dataset_key, created_at DESC);

GRANT ALL PRIVILEGES ON ml_training_runs TO brandpulse;
