"""RPA 定时监控 - 单次运行演示

用法: python main.py
流程: 启动演示目标服务 → 采集一轮 → 异常判定 → Excel 报表 → 告警输出
"""
import subprocess
import sys
import time
from pathlib import Path

import yaml

from monitor.collector import Collector
from monitor.detector import Detector
from monitor.history import History
from monitor.notifier import Notifier
from monitor.reporter import Reporter
from utils.logger import get_logger

BASE_DIR = Path(__file__).resolve().parent
logger = get_logger("rpa_monitor")
DEMO_PORT = 8100


def load_config() -> dict:
    with open(BASE_DIR / "config" / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_once(cfg: dict) -> list[dict]:
    targets = cfg["targets"]
    rules = cfg["rules"]
    storage = cfg["storage"]

    timeout = max(t.get("timeout", 10) for t in targets)
    collector = Collector(timeout=timeout)
    detector = Detector(rules["max_response_time"], rules["deviation_ratio"])
    notifier = Notifier(cfg.get("alert", {}).get("smtp", {}))
    reporter = Reporter(BASE_DIR / storage["report_dir"])
    history = History(BASE_DIR / storage["db_path"])

    # 1. 采集一轮
    samples = [collector.collect(t) for t in targets]

    # 2. 异常判定（结合上一次采样做环比）
    alerts = []
    for s in samples:
        prev = history.last_for(s["name"])
        is_alert, reason = detector.check(s, prev)
        if is_alert:
            alerts.append({**s, "error": reason})
            logger.warning(f"异常判定: {s['name']} -> {reason}")

    # 3. 保存历史 + 生成报表 + 告警
    history.save(samples)
    report = reporter.build(samples, alerts)
    notifier.send(alerts)

    logger.info(f"本次监控完成: {len(samples)} 个目标, {len(alerts)} 个异常")
    logger.info(f"报表已生成: {report}")
    return alerts


def main() -> int:
    cfg = load_config()
    python = sys.executable
    demo = subprocess.Popen(
        [python, str(BASE_DIR / "demo_server.py"), "--port", str(DEMO_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.5)  # 等待演示服务就绪
        run_once(cfg)
        return 0
    finally:
        demo.terminate()
        demo.wait()
        print("[*] 演示目标服务已关闭")


if __name__ == "__main__":
    sys.exit(main())
