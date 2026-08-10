-- 机器学习数据输入、训练日志和预测导出运行台账。
-- 上传数据仍然与 store_operations 隔离，生产资格默认关闭。

ALTER TABLE ml_training_runs
    ADD COLUMN IF NOT EXISTS dataset_upload_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS model_id VARCHAR(128);

CREATE TABLE IF NOT EXISTS ml_dataset_uploads (
    upload_id           VARCHAR(64) PRIMARY KEY,
    dataset_key         VARCHAR(128) NOT NULL UNIQUE,
    original_filename   VARCHAR(255) NOT NULL,
    stored_path         TEXT,
    file_format         VARCHAR(16) NOT NULL,
    data_origin         VARCHAR(64) NOT NULL DEFAULT 'user_upload',
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    sha256              VARCHAR(64),
    row_count           BIGINT,
    store_count         INT,
    item_count          INT,
    min_date            DATE,
    max_date            DATE,
    validation          JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              VARCHAR(16) NOT NULL DEFAULT 'valid',
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_dataset_uploads_created
    ON ml_dataset_uploads(created_at DESC);

CREATE TABLE IF NOT EXISTS ml_operation_logs (
    log_id              VARCHAR(64) PRIMARY KEY,
    operation_type      VARCHAR(32) NOT NULL,
    status              VARCHAR(16) NOT NULL,
    level               VARCHAR(16) NOT NULL DEFAULT 'info',
    run_id              VARCHAR(64),
    upload_id           VARCHAR(64),
    export_id           VARCHAR(64),
    message             TEXT NOT NULL,
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_operation_logs_created
    ON ml_operation_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ml_operation_logs_type
    ON ml_operation_logs(operation_type, created_at DESC);

CREATE TABLE IF NOT EXISTS ml_forecast_exports (
    export_id           VARCHAR(64) PRIMARY KEY,
    run_id              VARCHAR(64),
    model_id            VARCHAR(128) NOT NULL,
    file_format         VARCHAR(16) NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    rq_job_id           VARCHAR(128),
    file_path           TEXT,
    row_count           BIGINT,
    error               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    finished_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ml_forecast_exports_created
    ON ml_forecast_exports(created_at DESC);

GRANT ALL PRIVILEGES ON ml_dataset_uploads TO brandpulse;
GRANT ALL PRIVILEGES ON ml_operation_logs TO brandpulse;
GRANT ALL PRIVILEGES ON ml_forecast_exports TO brandpulse;
