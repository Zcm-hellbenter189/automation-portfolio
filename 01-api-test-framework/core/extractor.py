"""响应提取 + 变量池：支持接口间依赖传递

典型依赖链: 登录取 token → 创建用户取 user_id → 下单
用法:
  extracted = extract_variables(resp, {"user_id": "data.id"})
  variables.set("user_id", extracted["user_id"])
"""
import threading


class VariablePool:
    """线程安全的变量池，session 级共享（conftest 中注册）"""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock() # 线程锁，同一时刻只允许一个线程"持有"它

    def set(self, name: str, value):
        with self._lock:
            self._store[name] = value

    def get(self, name: str, default=None):
        with self._lock:
            return self._store.get(name, default)

    def all(self) -> dict:
        with self._lock:
            return dict(self._store)#新建字典拷贝一份，防止缓存污染


def extract_variables(resp, mapping: dict) -> dict:
    """按点号路径从响应 JSON 中提取值，token和id

    mapping 示例: {"user_id": "data.id", "token": "data.token"}
    """
    payload = resp.json()#把响应的JSON字符串，自动解析成Python字典/列表
    extracted = {}
    for name, path in mapping.items():
        node = payload
        for key in path.split("."):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        extracted[name] = node
    return extracted

