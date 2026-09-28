"""响应提取 + 变量池：支持接口间依赖传递

典型依赖链: 登录取 token → 创建用户取 user_id → 下单

用法:
  extracted = extract_variables(resp, {"user_id": "data.id"})
  variables.set("user_id", extracted["user_id"])

⚠️ 实测边界（细节见 docs/01-maturity-assessment.md）:
  - `VariablePool` 的**唯一实例化点**是 `conftest.py` 的 `auto_login` 夹具，
    唯一读取点是 `test_order.py`；其余用例声明 `auto_login` 只是为了拿它的**副作用**
    （把 token 注入共享 client）；
  - "session 级共享"靠的是 **pytest 的夹具缓存**（`scope="session"`），**不是**全局单例；
  - 内部 `threading.Lock` **只对同进程内的多线程有效**，对 `pytest-xdist` 的**多进程无效**。
"""
import threading


class VariablePool:
    """线程安全的键值容器，用于在用例之间传递上游接口提取出的数据

    生命周期：由 `conftest.py` 的 `auto_login`（`scope="session"`）创建并随夹具注入，
    整轮测试共享同一个实例。
    """

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock() # 线程锁，同一时刻只允许一个线程"持有"它

    def set(self, name: str, value) -> None:
        """写入一个变量（加锁）"""
        with self._lock:
            self._store[name] = value

    def get(self, name: str, default=None):
        """读取一个变量；不存在时返回 `default`（加锁）"""
        with self._lock:
            return self._store.get(name, default)

    def all(self) -> dict:
        """返回全部变量的**浅拷贝**（加锁）

        返回拷贝而非内部对象，避免调用方误改内部状态。
        """
        with self._lock:
            return dict(self._store)#新建字典拷贝一份，防止缓存污染


def extract_variables(resp, mapping: dict) -> dict:
    """按点号路径从响应 JSON 中提取值，供后续接口引用

    :param resp: requests 的 Response 对象（内部会调用 `resp.json()`）
    :param mapping: `{变量名: 点号路径}`，如 `{"user_id": "data.id", "token": "data.token"}`
    :return: `{变量名: 提取到的值}`

    行为：路径**逐层存在**才取值；**任何一层缺失就把该变量置为 `None`（不抛异常）** ——
         所以调用方拿到 None 时应自行断言（本项目 `auto_login` 就是这么做的）。
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

