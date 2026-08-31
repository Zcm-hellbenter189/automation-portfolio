"""演示目标服务：模拟多个被监控的接口（纯标准库）

GET /api/health   200，快速返回
GET /api/slow     200，但耗时 3 秒（用于触发"响应过慢"告警）
GET /api/error    500（用于触发"状态码异常"告警）

启动: python demo_server.py --port 8100
"""
import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默日志，避免干扰监控输出

    def _send(self, status, body: str = ""):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, "ok")
        elif self.path == "/api/slow":
            time.sleep(3)
            self._send(200, "slow-but-ok")
        elif self.path == "/api/error":
            self._send(500, "internal error")
        else:
            self._send(404, "not found")


def main():
    parser = argparse.ArgumentParser(description="演示目标服务")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"演示目标服务已启动: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n演示目标服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
