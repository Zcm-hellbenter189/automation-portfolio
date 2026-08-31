"""APScheduler 跨平台定时调度（Windows 下无需 cron）"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from utils.logger import get_logger

logger = get_logger("scheduler")


class MonitorScheduler:
    def __init__(self, job, interval_seconds: int = 60):
        self.scheduler = BlockingScheduler()
        self.job = job
        self.interval = interval_seconds

    def start(self):
        self.scheduler.add_job(self.job, IntervalTrigger(seconds=self.interval),
                               id="monitor", max_instances=1)
        logger.info(f"调度器已启动，每 {self.interval} 秒执行一次监控")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("调度器已停止")
