-- 告警规则表
CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    brand_id        VARCHAR(32),
    metric          VARCHAR(64) NOT NULL,
    operator        VARCHAR(8) NOT NULL CHECK (operator IN ('>', '<', '=', '>=', '<=')),
    threshold       DECIMAL(12, 4) NOT NULL,
    destinations    JSONB DEFAULT '[]'::jsonb,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_enabled ON alerts(enabled);
CREATE INDEX IF NOT EXISTS idx_alerts_brand ON alerts(brand_id);

-- 告警触发历史
CREATE TABLE IF NOT EXISTS alert_history (
    id              SERIAL PRIMARY KEY,
    alert_id        INT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    checked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered       BOOLEAN NOT NULL,
    metric_value    DECIMAL(12, 4),
    message         TEXT,
    sent_log        JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_alert_history_alert ON alert_history(alert_id);

GRANT ALL PRIVILEGES ON alerts, alert_history TO brandpulse;
GRANT ALL PRIVILEGES ON SEQUENCE alerts_id_seq, alert_history_id_seq TO brandpulse;
