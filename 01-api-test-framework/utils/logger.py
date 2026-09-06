"""结构化日志：控制台 + 文件双输出

设计要点:
  - 目录创建挪进 get_logger()（首次真正写日志时），
    消除"import 模块即产生磁盘副作用"的问题：
    静态分析/仅导入本模块都不会再在磁盘上建目录。
"""
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "reports"


def get_logger(name: str = "framework") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # 防止重复添加 handler
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger
