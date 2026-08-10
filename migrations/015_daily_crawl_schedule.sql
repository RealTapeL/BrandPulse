-- 将自动采集计划升级为“每天固定时间”执行。
-- 保留 interval_minutes 以兼容旧 API，但新调度逻辑以 run_hour/run_minute 为准。

ALTER TABLE crawl_schedules
    ADD COLUMN IF NOT EXISTS run_hour SMALLINT NOT NULL DEFAULT 9,
    ADD COLUMN IF NOT EXISTS run_minute SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    ADD COLUMN IF NOT EXISTS last_enqueued_for DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'crawl_schedules_run_hour_check'
    ) THEN
        ALTER TABLE crawl_schedules
            ADD CONSTRAINT crawl_schedules_run_hour_check
            CHECK (run_hour BETWEEN 0 AND 23);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'crawl_schedules_run_minute_check'
    ) THEN
        ALTER TABLE crawl_schedules
            ADD CONSTRAINT crawl_schedules_run_minute_check
            CHECK (run_minute BETWEEN 0 AND 59);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'crawl_schedules_timezone_check'
    ) THEN
        ALTER TABLE crawl_schedules
            ADD CONSTRAINT crawl_schedules_timezone_check
            CHECK (timezone IN ('Asia/Shanghai'));
    END IF;
END $$;

UPDATE crawl_schedules
SET last_enqueued_for = (last_enqueued_at AT TIME ZONE timezone)::date
WHERE last_enqueued_at IS NOT NULL
  AND last_enqueued_for IS NULL;

CREATE INDEX IF NOT EXISTS idx_crawl_schedules_daily_due
    ON crawl_schedules(enabled, last_enqueued_for, run_hour, run_minute);

GRANT ALL PRIVILEGES ON crawl_schedules TO brandpulse;
