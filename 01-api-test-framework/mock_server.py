"""
本地 Mock 接口服务（纯 Python 标准库实现，零第三方依赖）

启动: python mock_server.py --port 8000

提供接口:
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
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_PREFIX = "mock-token-"
ADMIN = {"username": "admin", "password": "123456"}


class MockHandler(BaseHTTPRequestHandler):
    """内存态存储放在类属性上，所有请求实例共享"""

    users = {}
    orders = {}
    next_user_id = 1
    next_order_id = 1001

    # ---------- 基础方法 ----------
    def log_message(self, fmt, *args):
        print(f"[mock] {self.address_string()} {fmt % args}")

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _is_authed(self):
        auth = self.headers.get("Authorization", "")
        return auth.startswith(TOKEN_PREFIX)

    # ---------- 路由 ----------
    def do_POST(self):
        if self.path == "/api/login":
            self._handle_login()
        elif self.path == "/api/users":
            self._handle_create_user()
        elif self.path == "/api/orders":
            self._handle_create_order()
        else:
            self._send(404, {"code": 1004, "msg": "接口不存在"})

    def do_GET(self):
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

    # ---------- 业务 handler ----------
    def _handle_login(self):
        body = self._read_json()
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            self._send(400, {"code": 1002, "msg": "缺少参数: username/password"})
            return
        if username == ADMIN["username"] and password == ADMIN["password"]:
            token = f"{TOKEN_PREFIX}{int(time.time())}a1b2c3"
            self._send(200, {"code": 0, "msg": "登录成功",
                             "data": {"token": token, "username": username}})
        else:
            self._send(401, {"code": 1001, "msg": "用户名或密码错误"})

    def _handle_create_user(self):
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        body = self._read_json()
        name = body.get("name")
        if not name:
            self._send(400, {"code": 1002, "msg": "缺少参数: name"})
            return
        uid = self.next_user_id
        self.next_user_id += 1
        self.users[uid] = {"id": uid, "name": name, "age": body.get("age", 0)}
        self._send(200, {"code": 0, "msg": "创建成功", "data": self.users[uid]})

    def _handle_list_users(self):
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        self._send(200, {"code": 0, "msg": "ok", "data": list(self.users.values())})

    def _handle_get_user(self):
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        try:
            uid = int(self.path.rsplit("/", 1)[-1])
        except ValueError:
            self._send(400, {"code": 1002, "msg": "用户 id 格式错误"})
            return
        user = self.users.get(uid)
        if user is None:
            self._send(404, {"code": 1003, "msg": "用户不存在"})
            return
        self._send(200, {"code": 0, "msg": "ok", "data": user})

    def _handle_create_order(self):
        if not self._is_authed():
            self._send(401, {"code": 1001, "msg": "未登录或登录已过期"})
            return
        body = self._read_json()
        user_id = body.get("user_id")
        product = body.get("product")
        if not user_id or not product:
            self._send(400, {"code": 1002, "msg": "缺少参数: user_id/product"})
            return
        if user_id not in self.users:
            self._send(400, {"code": 1005, "msg": "用户不存在，无法下单"})
            return
        order_id = self.next_order_id
        self.next_order_id += 1
        self.orders[order_id] = {
            "order_id": order_id,
            "user_id": user_id,
            "product": product,
            "amount": body.get("amount", 0),
        }
        self._send(200, {"code": 0, "msg": "下单成功", "data": self.orders[order_id]})


def main():
    parser = argparse.ArgumentParser(description="本地 Mock 接口服务")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), MockHandler)
    print(f"Mock 服务已启动: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMock 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
