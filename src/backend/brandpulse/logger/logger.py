"""
BrandPulse 日志工具

所有模块通过 get_logger(__name__) 获取 logger：
- 控制台实时输出（stdout）
- 同时写入项目根目录 logs/brandpulse.log（本地持久保存）
"""
import logging
import sys
from pathlib import Path

# 项目根目录（src/backend/brandpulse/logger/logger.py -> 上四级）
LOG_DIR = Path(__file__).resolve().parents[4] / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "brandpulse.log"


def get_logger(name: str, log_file: Path = None) -> logging.Logger:
    """
    获取统一格式的 logger（控制台 + 文件双写）

    Args:
        name: logger 名称，一般为 __name__
        log_file: 额外指定的日志文件；不传则默认写 logs/brandpulse.log
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出（默认 logs/brandpulse.log）
    path = Path(log_file) if log_file else DEFAULT_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
