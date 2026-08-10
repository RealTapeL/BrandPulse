-- Agent 后台任务改为 RQ 持久化队列执行。
-- 不删除历史任务；无法确认已进入队列的旧 pending 任务统一标记为失败，避免永久假运行。

ALTER TABLE agent_tasks
    ADD COLUMN IF NOT EXISTS rq_job_id     VARCHAR(64),
    ADD COLUMN IF NOT EXISTS started_at    TIMESTAMP,
    ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_rq_job
    ON agent_tasks(rq_job_id);

UPDATE agent_tasks
SET status = 'failed',
    error = COALESCE(NULLIF(error, ''), '历史任务未进入持久化队列，已终止，请重新提交'),
    updated_at = CURRENT_TIMESTAMP,
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
WHERE status = 'pending' AND rq_job_id IS NULL;

GRANT ALL PRIVILEGES ON agent_tasks TO brandpulse;
