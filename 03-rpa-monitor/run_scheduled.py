"""RPA 定时监控 - 常驻调度入口

用法: python run_scheduled.py
说明: 每 N 秒执行一次监控（间隔在 config/config.yaml 配置）。
      Windows 下可直接运行；也可注册为"任务计划程序"开机自启。
      Ctrl+C 停止。
"""
import subprocess
import sys
from pathlib import Path

from main import load_config, run_once
from scheduler.scheduler import MonitorScheduler
from utils.logger import get_logger

BASE_DIR = Path(__file__).resolve().parent
logger = get_logger("rpa_monitor")
DEMO_PORT = 8100


def main():
    python = sys.executable
    demo = subprocess.Popen(
        [python, str(BASE_DIR / "demo_server.py"), "--port", str(DEMO_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        cfg = load_config()
        scheduler = MonitorScheduler(
            job=lambda: run_once(cfg),
            interval_seconds=cfg["schedule"]["interval_seconds"],
        )
        scheduler.start()
    finally:
        demo.terminate()
        demo.wait()
        print("[*] 演示目标服务已关闭")


if __name__ == "__main__":
    main()
