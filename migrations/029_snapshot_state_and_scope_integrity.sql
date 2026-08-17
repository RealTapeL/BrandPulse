-- Phase 1：快照状态历史与可信范围一致性。
-- 不删除历史数据；历史快照回填为一次 migration 初始状态事件。

CREATE TABLE IF NOT EXISTS snapshot_status_history (
    history_id       VARCHAR(64) PRIMARY KEY,
    snapshot_id      VARCHAR(64) NOT NULL REFERENCES data_snapshots(snapshot_id) ON DELETE CASCADE,
    from_status      VARCHAR(24),
    to_status        VARCHAR(24) NOT NULL
                     CHECK (to_status IN ('draft', 'collecting', 'partial', 'validating', 'ready', 'published',
                                          'failed', 'rejected', 'expired', 'superseded')),
    reason           TEXT NOT NULL DEFAULT '',
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    transitioned_by  VARCHAR(64) NOT NULL DEFAULT 'system',
    transitioned_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshot_status_history_snapshot
    ON snapshot_status_history(snapshot_id, transitioned_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_observations_scope_category_date
    ON raw_observations(scope_id, standard_category, observed_date DESC);

CREATE INDEX IF NOT EXISTS idx_snapshot_source_results_source_status
    ON snapshot_source_results(source_name, status, observed_at DESC);

-- 为已经存在的快照补充可审计的初始状态，不改变快照当前状态。
INSERT INTO snapshot_status_history (
    history_id, snapshot_id, from_status, to_status, reason, metadata, transitioned_by, transitioned_at
)
SELECT
    'snapshot_history_migration_' || substr(md5(snapshot.snapshot_id || '|' || snapshot.status), 1, 40),
    snapshot.snapshot_id,
    NULL,
    snapshot.status,
    '由 029 迁移回填的历史快照初始状态',
    jsonb_build_object('migration', '029_snapshot_state_and_scope_integrity'),
    'migration',
    COALESCE(snapshot.created_at, CURRENT_TIMESTAMP)
FROM data_snapshots AS snapshot
ON CONFLICT (history_id) DO NOTHING;

-- 可信层的关系一致性必须在数据库层兜底，避免绕过仓储后把不同范围的数据串入同一快照。
CREATE OR REPLACE FUNCTION brandpulse_enforce_trusted_scope_consistency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_scope_id VARCHAR(64);
    expected_collection_run_id VARCHAR(64);
    expected_source_name VARCHAR(128);
BEGIN
    IF TG_TABLE_NAME = 'raw_observations' THEN
        IF NEW.collection_run_id IS NOT NULL THEN
            SELECT collection.scope_id
              INTO expected_scope_id
              FROM collection_runs AS collection
             WHERE collection.collection_run_id = NEW.collection_run_id;
            IF expected_scope_id IS NULL THEN
                RAISE EXCEPTION 'raw_observations.collection_run_id % 不存在', NEW.collection_run_id;
            END IF;
            IF NEW.scope_id IS DISTINCT FROM expected_scope_id THEN
                RAISE EXCEPTION '原始观测 scope_id 与 collection_run_id 不一致: %, %',
                    NEW.scope_id, NEW.collection_run_id;
            END IF;
        END IF;

        IF NEW.source_run_id IS NOT NULL THEN
            SELECT source.collection_run_id, source.source_name
              INTO expected_collection_run_id, expected_source_name
              FROM source_runs AS source
             WHERE source.source_run_id = NEW.source_run_id;
            IF expected_collection_run_id IS NULL THEN
                RAISE EXCEPTION 'raw_observations.source_run_id % 不存在', NEW.source_run_id;
            END IF;
            IF NEW.collection_run_id IS DISTINCT FROM expected_collection_run_id THEN
                RAISE EXCEPTION '原始观测 collection_run_id 与 source_run_id 不一致: %, %',
                    NEW.collection_run_id, NEW.source_run_id;
            END IF;
            IF NEW.source_name IS DISTINCT FROM expected_source_name THEN
                RAISE EXCEPTION '原始观测 source_name 与 source_run_id 不一致: %, %',
                    NEW.source_name, NEW.source_run_id;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'data_snapshots' THEN
        SELECT collection.scope_id
          INTO expected_scope_id
          FROM collection_runs AS collection
         WHERE collection.collection_run_id = NEW.collection_run_id;
        IF expected_scope_id IS NULL THEN
            RAISE EXCEPTION 'data_snapshots.collection_run_id % 不存在', NEW.collection_run_id;
        END IF;
        IF NEW.scope_id IS DISTINCT FROM expected_scope_id THEN
            RAISE EXCEPTION '快照 scope_id 与 collection_run_id 不一致: %, %',
                NEW.scope_id, NEW.collection_run_id;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'snapshot_source_results' THEN
        IF NEW.source_run_id IS NOT NULL THEN
            SELECT source.collection_run_id, source.source_name
              INTO expected_collection_run_id, expected_source_name
              FROM source_runs AS source
             WHERE source.source_run_id = NEW.source_run_id;
            IF expected_collection_run_id IS NULL THEN
                RAISE EXCEPTION 'snapshot_source_results.source_run_id % 不存在', NEW.source_run_id;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                  FROM data_snapshots AS snapshot
                 WHERE snapshot.snapshot_id = NEW.snapshot_id
                   AND snapshot.collection_run_id = expected_collection_run_id
            ) THEN
                RAISE EXCEPTION '来源结果与快照不属于同一 collection_run: %, %',
                    NEW.snapshot_id, NEW.source_run_id;
            END IF;
            IF NEW.source_name IS DISTINCT FROM expected_source_name THEN
                RAISE EXCEPTION '来源结果 source_name 与 source_run_id 不一致: %, %',
                    NEW.source_name, NEW.source_run_id;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'metric_observations' THEN
        SELECT snapshot.scope_id
          INTO expected_scope_id
          FROM data_snapshots AS snapshot
         WHERE snapshot.snapshot_id = NEW.snapshot_id;
        IF expected_scope_id IS NULL THEN
            RAISE EXCEPTION 'metric_observations.snapshot_id % 不存在', NEW.snapshot_id;
        END IF;
        IF NEW.scope_id IS DISTINCT FROM expected_scope_id THEN
            RAISE EXCEPTION '指标 scope_id 与 snapshot_id 不一致: %, %',
                NEW.scope_id, NEW.snapshot_id;
        END IF;
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_raw_observations_scope_consistency ON raw_observations;
CREATE TRIGGER trg_raw_observations_scope_consistency
BEFORE INSERT OR UPDATE OF scope_id, collection_run_id, source_run_id, source_name
ON raw_observations
FOR EACH ROW EXECUTE FUNCTION brandpulse_enforce_trusted_scope_consistency();

DROP TRIGGER IF EXISTS trg_data_snapshots_scope_consistency ON data_snapshots;
CREATE TRIGGER trg_data_snapshots_scope_consistency
BEFORE INSERT OR UPDATE OF scope_id, collection_run_id
ON data_snapshots
FOR EACH ROW EXECUTE FUNCTION brandpulse_enforce_trusted_scope_consistency();

DROP TRIGGER IF EXISTS trg_snapshot_source_results_consistency ON snapshot_source_results;
CREATE TRIGGER trg_snapshot_source_results_consistency
BEFORE INSERT OR UPDATE OF snapshot_id, source_run_id, source_name
ON snapshot_source_results
FOR EACH ROW EXECUTE FUNCTION brandpulse_enforce_trusted_scope_consistency();

DROP TRIGGER IF EXISTS trg_metric_observations_scope_consistency ON metric_observations;
CREATE TRIGGER trg_metric_observations_scope_consistency
BEFORE INSERT OR UPDATE OF snapshot_id, scope_id
ON metric_observations
FOR EACH ROW EXECUTE FUNCTION brandpulse_enforce_trusted_scope_consistency();

GRANT ALL PRIVILEGES ON snapshot_status_history TO brandpulse;
