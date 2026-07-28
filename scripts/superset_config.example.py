# Superset 本机配置
# 用法: export SUPERSET_CONFIG_PATH=/home/lsy/BrandPulse/scripts/superset_config.py

SECRET_KEY = "请用 openssl rand -base64 42 生成并填入"

# 元数据库（与 BrandPulse 业务库分开）
SQLALCHEMY_DATABASE_URI = (
    "postgresql://brandpulse:你的密码@localhost:5432/superset_meta"
)

# 本机开发环境
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = False

# 允许中文等
LANGUAGES = {
    "zh": {"flag": "cn", "name": "Chinese"},
    "en": {"flag": "us", "name": "English"},
}
BABEL_DEFAULT_LOCALE = "zh"

FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
}
