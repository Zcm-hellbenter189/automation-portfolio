"""
本地 Mock 接口服务（纯 Python 标准库实现，零第三方依赖）

启动: python mock_server.py --port 8000

提供接口:
  POST /api/register            公开注册（无需登录）
  POST /api/login               登录，成功返回 token
  GET  /api/users               用户列表（需要 Authorization）
  POST /api/users               创建用户
  GET  /api/users/{id}          查询用户
  POST /api/orders              下单（依赖已存在的 user_id）
  GET  /api/slow                慢响应 3 秒（演示响应时间断言）
  GET  /api/error               恒返回 500（演示异常场景）

设计意图: 本地 mock 保证「任何环境 clone 下来必定能跑通」，
         且能刻意构造 401/400/404/500/慢响应 等外网 API 难以稳定的场景。
"""
import argparse      # 命令行参数工具：解析 python mock_server.py --port 8000 里的 8000
import json          # JSON 序列化/解析：dict ↔ JSON 字符串
import threading     # 锁：保护共享的"内存数据库"不被并发写坏
import time          # 时间：登录时生成带时间戳的 token；/api/slow 里 sleep
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # 导入"服务员基类"和"前台服务器"两个类
TOKEN_PREFIX = "mock-token-"  # token 的统一前缀，鉴权就靠"开头是不是这个"来判断
ADMIN = {"username": "admin", "password": "123456"}  # 唯一的"合法账号"，写死在代码里（演示用）


class MockHandler(BaseHTTPRequestHandler):
    """内存态存储放在类属性上，所有请求实例共享

    并发安全: ThreadingHTTPServer 每个请求一个实例，
    自增 id 与字典写入统一由 _lock（类级）保护，避免并发重复 id。
    """

    users = {}  # "用户表"：{id: 用户dict}，全进程共享
    orders = {}  # "订单表"：{order_id: 订单dict}
    next_user_id = 1  # 下一个用户的 id（从 1 递增）
    next_order_id = 1001  # 下一个订单 id（从 1001 递增，故意和用户 id 区分开）
    _lock = threading.Lock()  # 一把共享锁（下划线开头=内部用）

    # ---------- 基础方法 ----------
    def log_message(self, fmt, *args):
        """输出mock服务控制台日志
        fmt为百分号格式化模板，*args为填充模板的可变参数。
        输出示例：[mock] 127.0.0.1:8000 method=POST path=/api/user code=200
        :param fmt: 带 %s/%d 占位符的日志模板字符串
        :param args: 待填入模板的可变参数元组
        """
        # address_string 获取服务地址端口；fmt % args 将参数填充到模板
        print(f"[mock] {self.address_string()} {fmt % args}")

    def _send(self, status, payload):
        """返回JSON格式HTTP响应
        :param status: HTTP状态码，如200、400
        :param payload: python字典/列表，要返回给客户端的业务数据
        - `Content‑Type`：告诉客户端：body 里面是什么格式的数据、用什么编码。
        -`Content‑Length`：告诉客户端：body 一共有多少字节，你从 socket 字节流里读完这么多字节，本次响应就结束。
        """
        # 将payload序列化为json字符串，转成utf‑8字节流。 HTTP传输只能传字节
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # # 写入状态行：HTTP/1.1 200 OK  →内存缓冲区
        self.send_response(status)
        # 设置响应头：返回数据为json，编码utf‑8，添加一条header到缓冲区
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # 设置响应体字节长度，浏览器/客户端用来解析报文
        self.send_header("Content-Length", str(len(body)))
        # 结束http响应头部分，内部会自动把所有header输出，输出之后不能再调用send_header()
        self.end_headers()
        #self.wfile是http输出字节流对象；write()只接收bytes，把json字节报文写回客户端
        self.wfile.write(body)

    def _read_json(self):
        """
        读取HTTP请求体中的JSON数据
        从请求头获取Content-Length，按长度读取rfile请求流，解码后解析json
        :return: dict，解析成功返回json字典；无请求体/解析失败返回空字典{}
        """
        # 获取请求体长度，取不到则默认为0
        length = int(self.headers.get("Content-Length") or 0)
        # 长度小于等于0，说明没有请求体，直接返回空字典
        if length <= 0:
            return {}
        try:
            # 读取指定字节流，utf-8解码，加载为json对象
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            # json格式错误时捕获异常，返回空字典
            return {}

    def _is_authed(self):
        """
        校验请求头是否携带符合前缀规范的Authorization鉴权头
        仅做格式校验：判断Authorization是否以TOKEN_PREFIX开头，不校验token本身有效性
        :return: bool布尔值，True=鉴权头格式合法；False=无Authorization或前缀不匹配
        """
        # 获取Authorization请求头，不存在则返回空字符串
        auth = self.headers.get("Authorization", "")
        # 判断字符串是否以指定前缀开头，返回布尔值（例如 "TOKEN_PREFIX"）
        return auth.startswith(TOKEN_PREFIX)

    def _parse_user_id(self):
        """从路径解析 id：成功返回 int，失败返回 None"""
        try:
            return int(self.path.rsplit("/", 1)[-1])
        except ValueError:
            return None

    # ---------- 路由 ----------
    def do_POST(self):
        """POST 请求的路由入口：按 URL 路径把请求分发给对应业务处理方法。

        触发方式：BaseHTTPRequestHandler(父类来自Python标准库) 收到 POST 请求时会自动调用本方法
        （命名约定 do_ + 请求方法名），因此在项目代码里看不到显式调用者。
        匹配规则：自上而下依次精确匹配 self.path；全部未命中则返回统一的 404。
        """
        # 公开注册：无需登录（和"登录后才能建用户"的后台操作区分开）
        if self.path == "/api/register":
            self._handle_register()
        # /api/login：登录，校验账号密码，成功则签发 token
        elif self.path == "/api/login":
            self._handle_login()
        # /api/users（POST 场景）：创建用户，需携带合法 Authorization
        elif self.path == "/api/users":
            self._handle_create_user()
        # /api/orders：下单，依赖已存在的 user_id，需登录
        elif self.path == "/api/orders":
            self._handle_create_order()
        else:
            # 未匹配任何已知接口：返回 404（HTTP 状态码 404 + 业务码 1004）
            self._send(404, {"code": 1004, "msg": "接口不存在"})

    def do_GET(self):
        """跟上面do_POST一样"""
        if self.path == "/api/users":
            self._handle_list_users()
        elif self.path.startswith("/api/users/"):
            self._handle_get_user()
        elif self.path == "/api/slow":
            time.sleep(3)
            self._send(200, {"code": 0, "msg": "ok", "data": {"elapsed_seconds": 3}})
        elif self.path == "/api/error":
            self._send(500, {"code": 5000, "msg": "服务器内部错误"})
        else:
            self._send(404, {"code": 1004, "msg": "接口不存在"})

    def do_PUT(self):
        """跟上面do_POST一样"""
        if self.path.startswith("/api/users/"):
            self._handle_update_user()


    # ---------- 业务 handler ----------
    def _handle_register(self):
        """公开注册接口处理

        与"创建用户"(POST /api/users) 的区别：
        - 本接口不校验 Authorization：陌生访客无需登录即可自助注册；
        - /api/users 需要登录，属于后台管理类的用户创建。
        校验顺序：读参 → name 必填 → 重名检查 → 加锁分配 id → 写用户表。
        """
        # 读取请求体 JSON（字段缺失时 get 返回 None）
        body = self._read_json()
        name = body.get("name")
        # name 为必填项，为空返回 400（先拦截后处理）
        if not name:
            self._send(400, {"code": 1002, "msg": "缺少参数: name"})
            return  # 提前结束，不再往下执行
        # 重名检查：users 表里已有同名用户则拒绝注册（业务码 1006）
        if any(u["name"] == name for u in self.users.values()):
            self._send(400, {"code": 1006, "msg": "用户名已存在"})
            return
        # 进入临界区：分配 id + 计数器递增 + 写入用户表，保证并发下 id 不重复
        with self._lock:
            # 必须用"类名直接 +="，才会更新类属性 next_user_id；
            # 若写 self.next_user_id += 1，会变成给"当前实例"建属性，
            # 而每个请求都是新实例，计数器会永远停在 1
            uid = MockHandler.next_user_id
            MockHandler.next_user_id += 1
            user = {"id": uid, "name": name, "age": body.get("age", 0)}  # age 缺省 0
            self.users[uid] = user  # 原地修改类级共享的 users 表（不是重新赋值）
        # 响应放在锁外写：避免持锁做网络 I/O，拖累其他线程的并发
        self._send(200, {"code": 0, "msg": "注册成功", "data": user})

    def _handle_login(self):
        """登录接口处理

        将请求体中的账号密码与内置 ADMIN 比对：
        - 缺 username / password 任一 → 400，业务码 1002
        - 账号密码匹配 → 200，业务码 0，data 内签发 token
        - 账号或密码错误 → 401，业务码 1001
        """
        # 读取请求体 JSON，字段缺失时 get 返回 None
        body = self._read_json()
        username = body.get("username")
        password = body.get("password")
        # 参数校验：任一为空直接返回 400（先拦截后处理）
        if not username or not password:
            self._send(400, {"code": 1002, "msg": "缺少参数: username/password"})
            return  # 提前结束本方法，避免继续往下走
        # 与内置账号比对
        if username == ADMIN["username"] and password == ADMIN["password"]:
            # 生成 token：前缀 + 当前秒级时间戳 + 固定尾缀，保证每次登录值不同
            token = f"{TOKEN_PREFIX}{int(time.time())}a1b2c3"
            self._send(200, {"code": 0, "msg": "登录成功",
                             "data": {"token": token, "username": username}})
        else:
            # 走到这里说明账号或密码至少有一项不匹配
            self._send(401, {"code": 1001, "msg": "用户名或密码错误"})

    def _handle_create_user(self):
        """创建用户接口处理

        处理流程：鉴权 → 读参数 → 校验 name 必填 → 加锁分配 id 并写入用户表。
        需携带合法 Authorization（已登录），否则直接返回 401。
        """
        # 第一步：鉴权，未登录立即拒绝
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        # 第二步：读取请求体
        body = self._read_json()
        name = body.get("name")
        # 第三步：name 为必填项，为空返回 400
        if not name:
            self._send(400, {"code": 1002, "msg": "缺少参数: name"})
            return
        # 第四步：进入临界区，保证并发请求下 id 不重复
        with self._lock:
            uid = MockHandler.next_user_id          # 取当前自增 id
            MockHandler.next_user_id += 1           # 计数器 +1，下次使用新 id
            user = {"id": uid, "name": name, "age": body.get("age", 0)}  # age 缺省为 0
            self.users[uid] = user           # 写入共享用户表
        # 第五步：返回创建成功及新用户数据
        self._send(200, {"code": 0, "msg": "创建成功", "data": user})

    def _handle_list_users(self):
        """查询用户列表接口处理

        入参：无（本接口不带查询参数，路径精确匹配 /api/users）
        鉴权：需要登录，未携带合法 Authorization 时返回 401 / 1001
        返回：data 为所有用户组成的列表（没有用户时为空列表）
        """
        # 鉴权前置校验：未登录直接拒绝，不继续往下执行
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        # users.values() 取出所有用户（dict 的值集合），list(...) 转成列表返回
        self._send(200, {"code": 0, "msg": "ok", "data": list(self.users.values())})

    def _handle_get_user(self):
        """查询单个用户接口处理（路径形如 /api/users/{id}）

        流程：鉴权 → 从路径解析 id → 查用户表 → 返回结果
        错误码：未登录 401/1001；id 非数字 400/1002；用户不存在 404/1003
        """
        # 鉴权前置校验：未登录直接拒绝
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        try:
            # 从路径末尾取 id："/api/users/5" → rsplit 切成 ["/api/users","5"] → 取 "5" → int 得 5
            uid = int(self.path.rsplit("/", 1)[-1])
        except ValueError:
            # 末尾不是数字（如 /api/users/abc）→ 参数格式错误，返回 400
            self._send(400, {"code": 1002, "msg": "用户 id 格式错误"})
            return
        # 用 get 而非 []：查不到返回 None，避免抛 KeyError 导致 500
        user = self.users.get(uid)
        if user is None:
            self._send(404, {"code": 1003, "msg": "用户不存在"})
            return
        # 命中用户，原样返回其信息
        self._send(200, {"code": 0, "msg": "ok", "data": user})

    def _handle_create_order(self):
        """下单接口处理（依赖已存在的 user_id，用于演示接口依赖链）

        流程：鉴权 → 读参 → 校验 user_id/product 必填 → 校验用户真实存在
              → 加锁分配订单号并写入订单表 → 返回订单信息
        错误码：未登录 401/1001；缺参数 400/1002；用户不存在 400/1005
        """
        # 鉴权前置校验：未登录直接拒绝
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        body = self._read_json()
        user_id = body.get("user_id")
        product = body.get("product")
        # 必填参数校验：任一为空直接返回 400
        if not user_id or not product:
            self._send(400, {"code": 1002, "msg": "缺少参数: user_id/product"})
            return
        # 业务校验：下单的用户必须已存在（该 id 通常来自上游"创建用户"接口的返回值）
        if user_id not in self.users:
            self._send(400, {"code": 1005, "msg": "用户不存在，无法下单"})
            return
        # 进入临界区：分配订单号 + 写订单表，保证并发下订单号唯一
        with self._lock:
            order_id = MockHandler.next_order_id   # 读类属性计数器（不能写 self.next_order_id += 1）
            MockHandler.next_order_id += 1         # 用类名自增，才会更新类属性而非实例属性
            order = {
                "order_id": order_id,
                "user_id": user_id,
                "product": product,
                "amount": body.get("amount", 0),   # 金额缺省为 0
            }
            self.orders[order_id] = order
        # 响应放在锁外写：避免持锁做网络 I/O，拖累并发
        self._send(200, {"code": 0, "msg": "下单成功", "data": order})

    def _handle_update_user(self):
        # 鉴权前置校验：未登录直接拒绝
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        body=self._read_json()
        name=body.get("name")
        age=body.get("age")
        if not name and not age:
            self._send(400, {"code": 1002, "msg": "缺少参数: name/age"})
            return
        uid=self._parse_user_id()
        if not uid:
            self._send(400, {"code": 1002, "msg": "用户 id 格式错误"})
            return
        user=self.users.get(uid)
        if user is None:
            self._send(404, {"code": 1003, "msg": "用户不存在"})
            return
        with self._lock:
            user["name"]=name
        if age:
            user["age"]=age
        self._send(200, {"code": 0, "msg": "更新成功", "data": user})


def main():
    """程序入口：解析端口参数 → 创建多线程 HTTP 服务 → 阻塞等待请求

    启动方式：python mock_server.py --port 8000
    """
    # 解析命令行参数：--port 不传时默认 8000
    parser = argparse.ArgumentParser(description="本地 Mock 接口服务")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # 创建服务器：监听 127.0.0.1:<port>，每个请求交给一个新的 MockHandler 实例处理
    server = ThreadingHTTPServer(("127.0.0.1", args.port), MockHandler)
    print(f"Mock 服务已启动: http://127.0.0.1:{args.port}")
    try:
        # 进入无限循环接收请求，直到用户按下 Ctrl+C
        server.serve_forever()
    except KeyboardInterrupt:
        # Ctrl+C 退出：打印提示并关闭服务器（释放端口）
        print("\nMock 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
