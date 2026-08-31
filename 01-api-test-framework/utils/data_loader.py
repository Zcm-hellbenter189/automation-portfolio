"""测试数据读取：yaml / json"""
import json
from pathlib import Path

import yaml


def load_yaml(path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
