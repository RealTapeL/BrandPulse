"""测试用 Bearer 会话；业务接口自此不再允许匿名调用。"""
from brandpulse.config.config import Config

# 测试使用本地业务库时默认不产生审计垃圾；审计契约测试会单独启用并精确清理。
# 不依赖开发者本机 .env 当前是否已切换到 rbac；RBAC 契约在 test_auth_rbac.py 中单独启用。
Config.AUTH_MODE = "local"
Config.AUDIT_ENABLED = False

from brandpulse.api.auth import create_access_token

AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test-operator')}"}
ADMIN_AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test-admin', role='admin')}"}
