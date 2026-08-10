-- 采集后台任务队列状态补全：记录 RQ job、开始时间和执行次数。
-- 不删除历史任务；无法确认入队的旧 pending 任务只标记为失败，保留原记录。

ALTER TABLE crawl_jobs
    ADD COLUMN IF NOT EXISTS rq_job_id     VARCHAR(64),
    ADD COLUMN IF NOT EXISTS started_at    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_rq_job
    ON crawl_jobs(rq_job_id);

UPDATE crawl_jobs
SET status = 'failed',
    result = COALESCE(NULLIF(result, ''), '{"error":"历史任务未进入持久化队列，已终止，请重新提交"}'),
    updated_at = CURRENT_TIMESTAMP,
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
WHERE status = 'pending'
  AND rq_job_id IS NULL
  AND created_at < CURRENT_TIMESTAMP - INTERVAL '10 minutes';

GRANT ALL PRIVILEGES ON crawl_jobs TO brandpulse;
