"""
BrandPulse 配置管理
统一从项目根目录的 .env 文件读取环境变量
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
PROJECT_ROOT = Path(__file__).resolve().parents[3]
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
