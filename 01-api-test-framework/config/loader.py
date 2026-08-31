"""配置加载：读取 config.yaml，支持 --env 选择环境，支持环境变量覆盖"""
import os
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"


def load_config(env: str = "dev") -> dict:
    """加载指定环境的配置片段"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    env_cfg = dict(raw.get(env, {}))
    # 可选：环境变量覆盖（用于 CI/CD 场景）
    if os.environ.get("BASE_URL"):
        env_cfg["base_url"] = os.environ["BASE_URL"]
    return env_cfg


def load_login() -> dict:
    """加载登录依赖的默认账号"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("login", {})
