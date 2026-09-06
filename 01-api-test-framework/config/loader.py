"""配置加载：读取 config.yaml，支持 --env 选择环境，支持环境变量覆盖

设计要点:
  - config.yaml 只在首次访问时解析一次并缓存（lru_cache），
    load_config / load_login 不再各自重复 open + safe_load；
  - 返回值一律 dict 拷贝，调用方修改不会污染缓存，也不会串到其他环境。
"""
import os
from functools import lru_cache
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"


@lru_cache(maxsize=1)
def _raw_config() -> dict:
    """读取并解析 config.yaml（进程内仅解析一次）"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {} #把文件解析成字典对象
    #load 可能执行 yaml 里的恶意代码，safe_load 只做纯数据解析

def load_config(env: str = "dev") -> dict:
    """加载指定环境的配置片段

    环境名必须是 config.yaml 的顶层 key（login 除外，属账号配置而非环境）。
    拼错环境会立即抛错，避免"静默回落默认值、误以为测的是目标环境"。
    """
    raw = _raw_config()
    if env == "login" or env not in raw:
        available = ", ".join(sorted(k for k in raw if k != "login"))
        raise ValueError(
            f"未知环境: {env!r}，可用环境: {available or '(config.yaml 为空)'}"
        )
    env_cfg = dict(raw[env])
    # 可选：环境变量覆盖（用于 CI/CD 场景）
    if os.environ.get("BASE_URL"):
        env_cfg["base_url"] = os.environ["BASE_URL"]
    return env_cfg


def load_login() -> dict:
    """加载登录依赖的默认账号（拷贝返回，防调用方污染缓存）"""
    return dict(_raw_config().get("login", {}))
