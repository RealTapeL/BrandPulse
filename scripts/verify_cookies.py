"""
验证 cookie 文件是否能被正确加载。

用法：
    source .venv/bin/activate
    python scripts/verify_cookies.py dianping
"""
import sys

from brandpulse.collectors.modules.cookie_loader import load_cookies


def main():
    domain = sys.argv[1] if len(sys.argv) > 1 else ""
    cookies = load_cookies(domain_filter=domain)
    print(f"共加载 {len(cookies)} 条 cookie")
    for c in cookies[:5]:
        print(f"  - {c['name']}: {c['domain']}")


if __name__ == "__main__":
    main()
