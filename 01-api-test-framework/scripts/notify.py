"""企业微信群机器人通知：构建失败时推送到群。

在 Jenkinsfile 的 failure 块里调用：
    bat '"%PYTHON%" scripts/notify.py'

环境变量：
    WECOM_WEBHOOK_KEY —— 机器人 key（由 Jenkins 凭据/全局环境变量注入，**不进仓库**）
    JOB_NAME / BUILD_NUMBER / BUILD_URL —— Jenkins 自动注入，用于拼消息

设计要点:
  - **key 只从环境变量读**：凭据不写进代码库，换 key 不用改代码；
  - **通知失败不影响构建**：异常一律吞掉、只打 warning —— 通知是锦上添花，
    不该让流水线「更红」（构建已经是 FAILURE，再抛异常只会污染日志、掩盖真正的失败原因）；
  - **没配 key 时静默跳过**：本地手动执行也不会报错。
"""
import os
import sys
from pathlib import Path

import requests

# scripts/ 位于项目根下，先把项目根加进 sys.path 才能 import utils
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.logger import get_logger  # noqa: E402

logger = get_logger("notify")

WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"


def send_wecom(content: str, key: str) -> None:
    """发送 markdown 消息到企业微信群；失败只告警、不抛出

    :param content: markdown 文本（企业微信单条上限 4096 字节，本项目内容很短）
    :param key: 机器人 webhook key
    """
    try:
        resp = requests.post(
            WEBHOOK_URL,
            params={"key": key},  # key 走 query 参数，不拼进日志字符串
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info("企业微信通知已发送")
        else:
            # 企业微信即使 HTTP 200 也会返回业务错误（key 无效、超频、内容超长等）
            logger.warning(f"企业微信返回业务错误: {data}")
    except Exception as e:  # noqa: BLE001 —— 故意兜底：通知失败绝不影响构建
        logger.warning(f"企业微信通知失败（已忽略，不影响构建）: {e}")


def main() -> int:
    key = os.environ.get("WECOM_WEBHOOK_KEY", "").strip()
    if not key:
        logger.info("未配置 WECOM_WEBHOOK_KEY，跳过企业微信通知")
        return 0

    job = os.environ.get("JOB_NAME", "未知任务")
    build = os.environ.get("BUILD_NUMBER", "?")
    url = os.environ.get("BUILD_URL", "")

    content = (
        f"**接口自动化测试失败** 🔴\n"
        f"> 任务：{job} #{build}\n"
        f"> [点击查看构建]({url})"
    )
    send_wecom(content, key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
