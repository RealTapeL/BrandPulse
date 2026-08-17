-- 快照绑定的指标事实、版本、比较池与计算台账。
-- 不改写旧 brand_indicators_daily / indicators；旧指标只供兼容读，新正式页面消费 metric_observations。

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_key          VARCHAR(128) PRIMARY KEY,
    display_name        VARCHAR(255) NOT NULL,
    metric_group        VARCHAR(32) NOT NULL
                        CHECK (metric_group IN ('stock', 'activity', 'quality', 'competition', 'trend')),
    description         TEXT NOT NULL,
    unit                VARCHAR(32) NOT NULL DEFAULT '',
    source_scope        VARCHAR(128) NOT NULL DEFAULT '',
    window_rule         VARCHAR(255) NOT NULL DEFAULT '',
    metric_version      VARCHAR(64) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metric_calculation_runs (
    metric_run_id       VARCHAR(64) PRIMARY KEY,
    snapshot_id         VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    metric_version      VARCHAR(64) NOT NULL,
    status              VARCHAR(24) NOT NULL
                        CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    input_summary       JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_count        INT NOT NULL DEFAULT 0 CHECK (output_count >= 0),
    failure_reason      TEXT NOT NULL DEFAULT '',
    started_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at         TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, metric_version)
);

CREATE INDEX IF NOT EXISTS idx_metric_runs_snapshot
    ON metric_calculation_runs(snapshot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS metric_observations (
    metric_observation_id VARCHAR(64) PRIMARY KEY,
    snapshot_id            VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    scope_id               VARCHAR(64) NOT NULL REFERENCES trusted_monitoring_scopes(scope_id),
    metric_run_id          VARCHAR(64) REFERENCES metric_calculation_runs(metric_run_id) ON DELETE SET NULL,
    metric_key             VARCHAR(128) NOT NULL REFERENCES metric_definitions(metric_key),
    metric_version         VARCHAR(64) NOT NULL,
    entity_type            VARCHAR(32) NOT NULL,
    entity_key             VARCHAR(512) NOT NULL,
    brand_id               VARCHAR(32) REFERENCES brands(brand_id) ON DELETE SET NULL,
    store_id               VARCHAR(64) REFERENCES stores(store_id) ON DELETE SET NULL,
    source_name            VARCHAR(128) NOT NULL DEFAULT '',
    time_window_days       INT,
    value                  NUMERIC(20, 6),
    unit                   VARCHAR(32) NOT NULL DEFAULT '',
    quality_status         VARCHAR(24) NOT NULL DEFAULT 'valid'
                           CHECK (quality_status IN ('valid', 'partial', 'insufficient_sample', 'not_comparable', 'rejected')),
    baseline_scope         JSONB NOT NULL DEFAULT '{}'::jsonb,
    baseline_level         VARCHAR(64) NOT NULL DEFAULT '',
    sample_size            INT,
    parameters             JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence               JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (snapshot_id, metric_key, entity_type, entity_key, source_name)
);

CREATE INDEX IF NOT EXISTS idx_metric_observations_scope_snapshot
    ON metric_observations(scope_id, snapshot_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_metric_observations_brand_snapshot
    ON metric_observations(brand_id, snapshot_id)
    WHERE brand_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_metric_observations_quality
    ON metric_observations(quality_status, metric_key, calculated_at DESC);

INSERT INTO metric_definitions (
    metric_key, display_name, metric_group, description, unit, source_scope, window_rule, metric_version
) VALUES
    ('dp_review_count_stock', '点评累计评价数', 'stock', '指定快照中点评搜索结果展示的累计评价数总和；不表示近期热度或销售。', '条', '点评 · 当前范围', '当前快照', 'snapshot-v2'),
    ('dp_store_count_observed', '点评观测门店数', 'stock', '指定快照中通过校验的点评门店观测数量；不等同于品牌全国门店总数。', '家', '点评 · 当前范围', '当前快照', 'snapshot-v2'),
    ('xhs_content_count_observed', '小红书公开内容数', 'stock', '指定快照中通过校验的小红书公开内容数量；仅在来源成功时输出。', '篇', '小红书 · 当前范围', '当前快照', 'snapshot-v2'),
    ('xhs_likes_stock', '小红书累计互动', 'stock', '指定快照中可获取点赞数的公开内容点赞合计；缺失互动不按零补齐。', '赞', '小红书 · 当前范围', '当前快照', 'snapshot-v2'),
    ('bayesian_reputation', '贝叶斯加权口碑', 'quality', '同商场同品类优先的点评加权口碑；样本不足时按记录的降级规则处理。', '分', '点评 · 门店', '当前快照', 'snapshot-v2'),
    ('dianping_review_share', '点评评价份额', 'competition', '当前快照中门店累计评价数 / 同范围全部点评门店累计评价数；分母、来源和范围均写入证据。', '比例', '点评 · 当前范围', '当前快照', 'snapshot-v2'),
    ('source_coverage_ratio', '来源覆盖率', 'quality', '满足成功状态的预期来源数量 / 预期来源数量；empty_validated 和 failed 不计为成功。', '比例', '快照来源', '当前快照', 'snapshot-v2'),
    ('entity_mapping_coverage', '实体映射覆盖率', 'quality', '已确认品牌或门店映射的原始观测占可用原始观测比例；未确认记录不进入品牌指标。', '比例', '原始观测', '当前快照', 'snapshot-v2'),
    ('dp_review_count_delta', '点评评价增量', 'activity', '两个可比快照之间累计评价数的差值；仅当来源完整、时间有序且累计数未下降时输出。', '条', '点评 · 当前范围', '相邻可比快照', 'snapshot-v2'),
    ('dp_review_count_growth_rate', '点评评价增长率', 'trend', '点评评价增量 / 前一可比快照累计评价数；不规则、缺失或下降数据不输出结论。', '比例', '点评 · 当前范围', '相邻可比快照', 'snapshot-v2')
ON CONFLICT (metric_key) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    metric_group = EXCLUDED.metric_group,
    description = EXCLUDED.description,
    unit = EXCLUDED.unit,
    source_scope = EXCLUDED.source_scope,
    window_rule = EXCLUDED.window_rule,
    metric_version = EXCLUDED.metric_version,
    updated_at = CURRENT_TIMESTAMP;

GRANT ALL PRIVILEGES ON metric_definitions, metric_calculation_runs, metric_observations TO brandpulse;
