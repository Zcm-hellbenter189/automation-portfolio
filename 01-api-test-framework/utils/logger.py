"""结构化日志：文件落盘 + 交给 pytest 捕获（避免报告重复）

设计要点:
  - 目录创建挪进 get_logger()（首次真正写日志时），
    消除"import 模块即产生磁盘副作用"的问题：
    静态分析/仅导入本模块都不会再在磁盘上建目录。

  - 为什么默认不再往控制台(stderr)写日志：
    pytest 运行时，日志会被**两条独立通道**各捕获一次——
      ① stderr 捕获（StreamHandler 输出）    → 报告里的 "Captured stderr xxx"
      ② logging 捕获（日志向上传播到 root）   → 报告里的 "Captured log xxx"
    同一行日志因此出现两份。而 pytest-html 是直接渲染 report.sections 的，
    **完全不读 --show-capture 选项**，所以在 pytest.ini 里调参数没用，
    只能从源头关掉 stderr 这一路。

  - 非 pytest 环境（直接跑脚本 / 手工调试）仍保留控制台输出，不影响人工观察。
"""
import logging
import sys
from pathlib import Path

# 项目根目录（本文件在 utils/ 下，向上两级即项目根）
BASE_DIR = Path(__file__).resolve().parent.parent
# 日志输出目录：项目根下的 reports/（该目录已在 .gitignore 中，属运行产物）
LOG_DIR = BASE_DIR / "reports"


def get_logger(name: str = "framework") -> logging.Logger:
    """获取（或创建）一个日志落盘、并交由 pytest 捕获的 Logger

    :param name: logger 名称，同时决定日志文件名 reports/<name>.log
                 （如 http_client → reports/http_client.log）
    :return: logging.Logger 实例，支持 info / warning / error 等方法

    设计要点:
      - 同名 logger 只初始化一次（已有 handler 就直接返回），避免日志重复打印；
      - 文件始终落盘；日志同时向上传播，由 pytest 捕获写入测试报告；
      - 仅非 pytest 环境才挂控制台 handler（原因见模块 docstring）；
      - 目录创建放在这里（首次真正写日志时），避免 import 模块就产生磁盘副作用。
    """
    # 按名字取 logger：标准库内部以名字为 key 缓存，同名多次调用返回同一对象
    logger = logging.getLogger(name)
    if logger.handlers:  # 防止重复添加 handler（否则同一行日志会打印多次）
        return logger
    # 记录 INFO 及以上级别（需要更详细可改为 logging.DEBUG）
    logger.setLevel(logging.INFO)
    # 日志格式：时间 | 级别 | logger 名 | 消息
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    # ---------- 输出口 1：控制台（仅非 pytest 环境挂载） ----------
    # 判据：pytest 运行时 pytest 模块必然已在 sys.modules 中。
    # 挂载后日志会被 pytest 的捕获机制记成 "Captured stderr"，
    # 与它通过 logging 捕获的 "Captured log" 内容一字不差，报告里就是两份重复。
    if "pytest" not in sys.modules:
        console = logging.StreamHandler()   # 默认写 stderr，便于直接跑脚本时观察
        console.setFormatter(fmt)
        logger.addHandler(console)

    # ---------- 输出口 2：文件 ----------
    # parents=True：父目录不存在也一起建（等价 mkdir -p）；
    # exist_ok=True：目录已存在不报 FileExistsError
    LOG_DIR.mkdir(parents=True, exist_ok=True)   # 惰性建目录：首次写日志时才创建
    # 文件名为 <name>.log，追加模式（默认 a）：多次运行日志会累积，便于回溯历史
    file_handler = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger

