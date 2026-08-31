"""告警通知：默认日志 + Excel 告警页；可选 SMTP 邮件（默认关闭，避免误发骚扰）"""
import smtplib
from email.mime.text import MIMEText

from utils.logger import get_logger

logger = get_logger("notifier")


class Notifier:
    def __init__(self, smtp_cfg: dict | None = None):
        self.smtp = smtp_cfg or {}
        self.enabled = bool(self.smtp.get("enabled"))

    def send(self, alerts: list[dict]):
        if not alerts:
            logger.info("本次无告警")
            return
        for a in alerts:
            logger.error(f"[告警] {a['name']} | {a['error']} | {a['timestamp']}")
        if self.enabled:
            self._send_mail(alerts)

    def _send_mail(self, alerts: list[dict]):
        try:
            host, port = self.smtp["host"], int(self.smtp["port"])
            user, password = self.smtp["user"], self.smtp["password"]
            to = self.smtp["to"]
            lines = "\n".join(f"{a['name']} | {a['error']}" for a in alerts)
            msg = MIMEText(f"监控告警（{len(alerts)} 个目标异常）:\n\n{lines}", "plain", "utf-8")
            msg["Subject"] = f"[RPA监控告警] {len(alerts)} 个目标异常"
            msg["From"] = user
            msg["To"] = to

            if port == 465:
                server = smtplib.SMTP_SSL(host, port)
            else:
                server = smtplib.SMTP(host, port)
                server.starttls()
            server.login(user, password)
            server.send_message(msg)
            server.quit()
            logger.info("告警邮件已发送")
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
