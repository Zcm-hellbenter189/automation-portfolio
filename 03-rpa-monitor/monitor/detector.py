"""异常判定：非期望状态 / 请求失败 / 响应过慢 / 环比波动"""
from utils.logger import get_logger

logger = get_logger("detector")


class Detector:
    def __init__(self, max_response_time: float = 3.0, deviation_ratio: float = 0.5):
        self.max_response_time = max_response_time
        self.deviation_ratio = deviation_ratio

    def check(self, sample: dict, prev: dict | None) -> tuple[bool, str]:
        """返回 (是否异常, 告警原因)；prev 为上一次采样，用于环比波动判定"""
        if sample["status"] == -1:
            return True, sample["error"]
        if sample.get("error"):
            return True, sample["error"]
        if sample["elapsed"] > self.max_response_time:
            return True, f"响应过慢: {sample['elapsed']}s > {self.max_response_time}s"
        if prev is not None and prev.get("elapsed"):
            base = max(prev["elapsed"], 0.001)
            ratio = abs(sample["elapsed"] - prev["elapsed"]) / base
            if ratio > self.deviation_ratio:
                return True, f"响应时间环比波动 {ratio:.0%} > {self.deviation_ratio:.0%}"
        return False, ""
