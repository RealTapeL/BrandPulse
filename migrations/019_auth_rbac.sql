-- 生产级认证与三角色 RBAC：用户只保存密码哈希，会话只保存刷新令牌摘要。

CREATE TABLE IF NOT EXISTS auth_users (
    user_id               VARCHAR(36) PRIMARY KEY,
    username              VARCHAR(64) NOT NULL,
    username_normalized   VARCHAR(64) NOT NULL UNIQUE,
    password_hash         TEXT NOT NULL,
    role                  VARCHAR(16) NOT NULL
                          CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password  BOOLEAN NOT NULL DEFAULT TRUE,
    auth_revision         INTEGER NOT NULL DEFAULT 1,
    failed_login_count    SMALLINT NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until          TIMESTAMP,
    last_login_at         TIMESTAMP,
    password_changed_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            VARCHAR(36),
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_users_active_role
    ON auth_users(is_active, role);

CREATE TABLE IF NOT EXISTS auth_refresh_sessions (
    session_id            VARCHAR(36) PRIMARY KEY,
    user_id               VARCHAR(36) NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
    refresh_token_digest  CHAR(64) NOT NULL UNIQUE,
    issued_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at            TIMESTAMP NOT NULL,
    last_used_at          TIMESTAMP,
    revoked_at            TIMESTAMP,
    revoke_reason         VARCHAR(128),
    client_ip             VARCHAR(64) NOT NULL DEFAULT '',
    user_agent            VARCHAR(512) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active
    ON auth_refresh_sessions(user_id, expires_at DESC)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
    ON auth_refresh_sessions(expires_at);

-- 后台 Agent 任务必须保留请求主体和提交时允许的能力，Worker 不得自行假定管理员身份。
ALTER TABLE agent_tasks
    ADD COLUMN IF NOT EXISTS actor_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS actor_username VARCHAR(64),
    ADD COLUMN IF NOT EXISTS actor_role VARCHAR(16),
    ADD COLUMN IF NOT EXISTS allowed_tools JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_agent_tasks_actor_created
    ON agent_tasks(actor_id, created_at DESC);

GRANT ALL PRIVILEGES ON auth_users, auth_refresh_sessions TO brandpulse;
