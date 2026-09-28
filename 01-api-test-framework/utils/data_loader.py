"""测试数据读取：yaml"""
import yaml


def load_yaml(path):
    """读取 YAML 文件并返回 Python 对象

    :param path: 文件路径（`str` 或 `pathlib.Path`）
    :return: **取决于文件结构** —— 顶层是映射时返回 `dict`，顶层是列表时返回 `list`；
             空文件返回 `{}`。

    ⚠️ 不做任何异常包装：文件不存在 / YAML 语法错误会**直接抛出**
    （`FileNotFoundError` / `yaml.YAMLError`），由调用方或 pytest 呈现原始报错。
    """
    # 把 yaml 文本变成 Python dict/list
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
