-- Web 平台接入：Agent 异步任务与自定义指标公式。

CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id     VARCHAR(36) PRIMARY KEY,
    prompt      TEXT NOT NULL,
    context     JSONB NOT NULL DEFAULT '{}'::jsonb,
    status      VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
    output      TEXT,
    error       TEXT,
    logs        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status, created_at DESC);

CREATE TABLE IF NOT EXISTS custom_formulas (
    formula_id  VARCHAR(36) PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(200) NOT NULL DEFAULT '',
    expression  VARCHAR(500) NOT NULL,
    params      JSONB NOT NULL DEFAULT '[]'::jsonb,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    remark      VARCHAR(200) NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_custom_formulas_enabled ON custom_formulas(enabled);

GRANT ALL PRIVILEGES ON agent_tasks, custom_formulas TO brandpulse;
