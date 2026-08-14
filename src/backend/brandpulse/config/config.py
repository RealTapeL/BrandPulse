"""
BrandPulse 配置管理
统一从项目根目录的 .env 文件读取环境变量
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


class Config:
    """配置类"""

    # PostgreSQL（全系统唯一数据库）
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER", "brandpulse")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "brandpulse123")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "brandpulse")

    # Redis（任务队列与缓存）
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    # Web 平台登录。默认 local 模式仅用于单团队本地部署，严格模式由环境变量提供凭据。
    AUTH_MODE = os.getenv("AUTH_MODE", "local").lower()
    AUTH_USERNAME = os.getenv("AUTH_USERNAME", "")
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
    AUTH_SECRET = os.getenv("AUTH_SECRET", "")
    AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
    AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}

    # 逗号分隔的浏览器来源；allow_credentials=True 时不能使用通配符。
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    ]

    # 告警调度与通知
    ALERT_SCHEDULER_ENABLED = os.getenv("ALERT_SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes"}
    ALERT_INTERVAL_MINUTES = int(os.getenv("ALERT_INTERVAL_MINUTES", "5"))
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
    ALERT_WEBHOOK_TIMEOUT = float(os.getenv("ALERT_WEBHOOK_TIMEOUT", "10"))

    # 自动采集与报告计划。计划本身默认禁用；调度器只领取用户显式启用的计划。
    MONITORING_SCHEDULER_ENABLED = os.getenv("MONITORING_SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes"}
    MONITORING_SCHEDULER_INTERVAL_SECONDS = int(os.getenv("MONITORING_SCHEDULER_INTERVAL_SECONDS", "60"))
    REPORT_MAX_DATA_AGE_HOURS = int(os.getenv("REPORT_MAX_DATA_AGE_HOURS", "72"))

    # PostgreSQL 备份状态（备份脚本与生产配置自检共用）。
    _backup_dir_env = os.getenv("BRANDPULSE_BACKUP_DIR", "backups/postgres")
    BACKUP_DIR = (
        PROJECT_ROOT / _backup_dir_env
        if not Path(_backup_dir_env).is_absolute()
        else Path(_backup_dir_env)
    )
    BACKUP_RETENTION_DAYS = int(os.getenv("BRANDPULSE_BACKUP_RETENTION_DAYS", "14"))

    # 高德 API
    AMAP_KEY = os.getenv("AMAP_KEY", "")

    # LLM / Embedding 配置（OpenAI 兼容接口）
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
    DEFAULT_VECTOR_SIZE = int(os.getenv("DEFAULT_VECTOR_SIZE", "1536"))

    # 第三方搜索 API（BettaFish 思路：把反爬交给搜索服务商）
    # Bocha: https://open.bocha.cn
    BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
    BOCHA_BASE_URL = os.getenv("BOCHA_BASE_URL", "https://api.bocha.cn/v1/web-search")
    # Tavily: https://tavily.com
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    TAVILY_BASE_URL = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com/search")

    # Agent-Reach 外部研究能力。默认关闭，不替代 BrandPulse 真实数据采集链路。
    AGENT_REACH_ENABLED = os.getenv("AGENT_REACH_ENABLED", "false").lower() in {"1", "true", "yes"}
    AGENT_REACH_COMMAND = os.getenv("AGENT_REACH_COMMAND", "agent-reach")
    AGENT_REACH_SEARCH_COMMAND = os.getenv("AGENT_REACH_SEARCH_COMMAND", "mcporter")
    AGENT_REACH_TIMEOUT_SECONDS = int(os.getenv("AGENT_REACH_TIMEOUT_SECONDS", "30"))
    AGENT_REACH_MAX_RESPONSE_CHARS = int(os.getenv("AGENT_REACH_MAX_RESPONSE_CHARS", "12000"))

    # 项目路径
    DATA_DIR = PROJECT_ROOT / "data"
    RAW_DIR = DATA_DIR / "raw"
    PROCESSED_DIR = DATA_DIR / "processed"
    DEBUG_DIR = RAW_DIR / "debug"

    # 本地文件缓存路径（用于替代/备份 PostgreSQL metrics）
    # 相对路径基于项目根目录解析
    _metrics_cache_dir_env = os.getenv("METRICS_CACHE_DIR", str(PROCESSED_DIR))
    METRICS_CACHE_DIR = (
        PROJECT_ROOT / _metrics_cache_dir_env
        if not Path(_metrics_cache_dir_env).is_absolute()
        else Path(_metrics_cache_dir_env)
    )

    @classmethod
    def postgres_dsn(cls) -> str:
        """PostgreSQL 连接字符串"""
        return (
            f"postgresql://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
            f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"
        )

    @classmethod
    def ensure_dirs(cls) -> None:
        """确保数据目录存在"""
        cls.RAW_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        cls.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
