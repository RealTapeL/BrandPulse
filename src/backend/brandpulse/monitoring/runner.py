"""独立的自动采集/报告调度进程入口。

调度器不再依赖 FastAPI 生命周期。API 重启、前端发布或多进程部署时，
自动计划仍由这个单独进程负责；数据库原子领取保证同一计划不会重复入队。
"""

from __future__ import annotations

import signal
from threading import Event

from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger
from brandpulse.monitoring.scheduler import (
    shutdown_monitoring_scheduler,
    start_monitoring_scheduler,
)

logger = get_logger(__name__)


def run() -> None:
    if not Config.MONITORING_SCHEDULER_ENABLED:
        logger.warning("[monitoring] MONITORING_SCHEDULER_ENABLED=false，独立调度器不启动")
        return

    stop_event = Event()

    def stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    start_monitoring_scheduler(Config.MONITORING_SCHEDULER_INTERVAL_SECONDS)
    logger.info("[monitoring] 独立调度服务已启动")
    try:
        stop_event.wait()
    finally:
        shutdown_monitoring_scheduler()
        logger.info("[monitoring] 独立调度服务已停止")


if __name__ == "__main__":
    run()
