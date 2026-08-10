"""测试用 Bearer 会话；业务接口自此不再允许匿名调用。"""
from brandpulse.api.auth import create_access_token

AUTH_HEADERS = {"Authorization": f"Bearer {create_access_token('test-operator')}"}
