-- API 操作审计：不保存请求体、密码、Token 或业务文件内容。

CREATE TABLE IF NOT EXISTS audit_events (
    event_id      VARCHAR(64) PRIMARY KEY,
    request_id    VARCHAR(128) NOT NULL,
    actor_id      VARCHAR(64) NOT NULL DEFAULT 'anonymous',
    actor_role    VARCHAR(32) NOT NULL DEFAULT '',
    action        VARCHAR(320) NOT NULL,
    method        VARCHAR(8) NOT NULL,
    route         VARCHAR(255) NOT NULL,
    request_path  VARCHAR(512) NOT NULL,
    status_code   INT NOT NULL,
    outcome       VARCHAR(16) NOT NULL
                  CHECK (outcome IN ('success', 'failure')),
    client_ip     VARCHAR(64) NOT NULL DEFAULT '',
    duration_ms   NUMERIC(12, 3) NOT NULL DEFAULT 0,
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_events_created
    ON audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor
    ON audit_events(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_action
    ON audit_events(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_request
    ON audit_events(request_id);

GRANT ALL PRIVILEGES ON audit_events TO brandpulse;
