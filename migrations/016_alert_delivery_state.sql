-- 告警状态机与可靠通知投递。
-- 扩展配置与事件使用独立表，应用迁移账号无需成为历史表的 owner。

CREATE TABLE IF NOT EXISTS alert_delivery_policies (
    alert_id          INT PRIMARY KEY REFERENCES alerts(id) ON DELETE CASCADE,
    cooldown_minutes  INT NOT NULL DEFAULT 60
                      CHECK (cooldown_minutes BETWEEN 5 AND 10080),
    notify_recovery   BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_states (
    alert_id       INT PRIMARY KEY REFERENCES alerts(id) ON DELETE CASCADE,
    is_active      BOOLEAN NOT NULL DEFAULT FALSE,
    activated_at  TIMESTAMP,
    last_event_at TIMESTAMP,
    last_checked_at TIMESTAMP,
    last_value     DECIMAL(18, 6),
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_delivery_events (
    history_id          INT PRIMARY KEY REFERENCES alert_history(id) ON DELETE CASCADE,
    alert_id            INT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    event_type          VARCHAR(16) NOT NULL DEFAULT 'check',
    notification_status VARCHAR(24) NOT NULL DEFAULT 'not_requested',
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alert_delivery_events_alert
    ON alert_delivery_events(alert_id, history_id DESC);

CREATE TABLE IF NOT EXISTS alert_notification_deliveries (
    delivery_id       BIGSERIAL PRIMARY KEY,
    history_id        INT NOT NULL REFERENCES alert_history(id) ON DELETE CASCADE,
    alert_id          INT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    event_type        VARCHAR(16) NOT NULL,
    destination_type  VARCHAR(16) NOT NULL,
    destination_value TEXT NOT NULL,
    subject           VARCHAR(255) NOT NULL,
    message           TEXT NOT NULL,
    status            VARCHAR(16) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'sending', 'retry', 'sent', 'failed', 'cancelled')),
    attempt_count     INT NOT NULL DEFAULT 0,
    max_attempts      INT NOT NULL DEFAULT 5,
    next_attempt_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error        TEXT,
    response          JSONB NOT NULL DEFAULT '{}'::jsonb,
    sent_at           TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (history_id, destination_type, destination_value)
);

CREATE INDEX IF NOT EXISTS idx_alert_delivery_due
    ON alert_notification_deliveries(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_alert_delivery_alert
    ON alert_notification_deliveries(alert_id, created_at DESC);

GRANT ALL PRIVILEGES ON alert_delivery_policies, alert_states,
    alert_delivery_events, alert_notification_deliveries TO brandpulse;
GRANT ALL PRIVILEGES ON SEQUENCE alert_notification_deliveries_delivery_id_seq TO brandpulse;
