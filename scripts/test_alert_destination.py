#!/usr/bin/env python3
"""向真实告警目的地发送一条测试通知。

该脚本不会写数据库，也不会返回 mock 成功；只有 SMTP/Webhook 实际返回成功
才会以 0 退出。邮件使用项目 .env 中的 SMTP 配置，Webhook URL 由调用者显式传入。
"""

from __future__ import annotations

import argparse
import json
import sys

from brandpulse.alerts.sender import send_email, send_webhook


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 BrandPulse 真实告警通知通道")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="接收测试邮件的地址，SMTP 使用项目 .env 配置")
    group.add_argument("--webhook", help="接收测试通知的 http:// 或 https:// 地址")
    parser.add_argument("--message", default="BrandPulse 告警通道测试：这是一条真实发送的验证消息。")
    args = parser.parse_args()

    try:
        if args.email:
            result = send_email(args.email, "BrandPulse 告警通道测试", args.message)
        else:
            result = send_webhook(args.webhook, {"message": args.message, "source": "brandpulse-alert-test"})
    except Exception as exc:
        print(f"通知发送失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
