"""测试用 Bearer 会话；业务接口自此不再允许匿名调用。"""
from brandpulse.config.config import Config

# 测试使用本地业务库时默认不产生审计垃圾；审计契约测试会单独启用并精确清理。
Config.AUDIT_ENABLED = False

from brandpulse.api.auth import create_access_token

AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test-operator')}"}
