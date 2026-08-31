"""robots.txt 合规校验（红线模块）

启动前真实拉取目标站点的 robots.txt 并解析，
被禁止的路径直接拒绝运行 —— 合规是作品的底线，也是差异化亮点。
标准库 urllib.robotparser 实现，零第三方依赖。
"""
import urllib.robotparser

from utils.logger import get_logger

logger = get_logger("robots_checker")


class RobotsChecker:
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent

    def check(self, robots_url: str, url: str) -> bool:
        """返回 True 表示允许抓取该 URL。

        注意: robots.txt 不存在（404）时，按 robots 协议默认视为允许。
        """
        if not robots_url:
            return True
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
            allowed = rp.can_fetch(self.user_agent, url)
        except Exception as e:  # 拉取失败时保守处理：记录并放行交由 fetcher 容错
            logger.warning(f"robots.txt 读取失败（{e}），按默认允许处理")
            return True
        logger.info(f"robots.txt 判定: 目标 {url} -> {'允许' if allowed else '禁止'}")
        return allowed
