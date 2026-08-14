"""独立告警调度进程入口。

告警检查不能依赖 FastAPI 生命周期。生产环境可能运行多个 API 副本，
如果每个 API 进程都启动 APScheduler，会造成重复检查和重复通知；本 runner
作为单独进程运行，统一消费启用中的告警规则。
"""

from __future__ import annotations

import signal
from threading import Event

from brandpulse.alerts.scheduler import shutdown_scheduler, start_scheduler
from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def run() -> None:
    if not Config.ALERT_SCHEDULER_ENABLED:
        logger.warning("[alerts] ALERT_SCHEDULER_ENABLED=false，独立告警调度器不启动")
        return

    stop_event = Event()

    def stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    start_scheduler(Config.ALERT_INTERVAL_MINUTES)
    logger.info("[alerts] 独立告警调度服务已启动，间隔 %s 分钟", Config.ALERT_INTERVAL_MINUTES)
    try:
        stop_event.wait()
    finally:
        shutdown_scheduler()
        logger.info("[alerts] 独立告警调度服务已停止")


if __name__ == "__main__":
    run()
