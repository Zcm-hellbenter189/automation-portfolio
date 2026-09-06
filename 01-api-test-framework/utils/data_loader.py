"""测试数据读取：yaml"""
import yaml


def load_yaml(path) -> dict:
    #把 yaml 文本变成 Python dict/list
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
