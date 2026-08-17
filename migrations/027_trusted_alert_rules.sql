-- 可信告警：新规则必须绑定城市×商场×品类 scope，并且读取同一 scope 的快照指标。
-- 保留 alerts 及其投递/状态历史，避免破坏旧接口；没有本表配置的历史规则只标记为 legacy_unscoped，
-- 不会由新调度器自动执行，也不会被新页面表述为可信范围告警。

CREATE TABLE IF NOT EXISTS trusted_alert_rules (
    alert_id          INT PRIMARY KEY REFERENCES alerts(id) ON DELETE CASCADE,
    scope_id          VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    metric_key        VARCHAR(128) NOT NULL REFERENCES metric_definitions(metric_key),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trusted_alert_rules_scope
    ON trusted_alert_rules(scope_id, metric_key);

-- 每次可信告警检查固定记录触发时使用的快照和指标证据；旧 alert_history 表保持兼容。
CREATE TABLE IF NOT EXISTS trusted_alert_evaluations (
    history_id        INT PRIMARY KEY REFERENCES alert_history(id) ON DELETE CASCADE,
    alert_id          INT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    scope_id          VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    snapshot_id       VARCHAR(64) REFERENCES data_snapshots(snapshot_id) ON DELETE SET NULL,
    metric_key        VARCHAR(128) NOT NULL REFERENCES metric_definitions(metric_key),
    metric_quality    VARCHAR(24) NOT NULL DEFAULT 'valid',
    evidence          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trusted_alert_evaluations_scope_snapshot
    ON trusted_alert_evaluations(scope_id, snapshot_id, created_at DESC);

GRANT ALL PRIVILEGES ON trusted_alert_rules, trusted_alert_evaluations TO brandpulse;
