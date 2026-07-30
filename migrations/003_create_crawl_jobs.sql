-- crawl_jobs 表：抓取任务队列持久化
CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id      VARCHAR(64) PRIMARY KEY,
    brand_id    VARCHAR(32) NOT NULL,
    mall        VARCHAR(128) NOT NULL,
    category    VARCHAR(64) NOT NULL,
    cities      TEXT[],
    status      VARCHAR(32) NOT NULL DEFAULT 'pending',
    result      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_brand ON crawl_jobs(brand_id);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);

GRANT ALL PRIVILEGES ON crawl_jobs TO brandpulse;
