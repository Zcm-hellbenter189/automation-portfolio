"""本地演示站点：纯标准库起一个静态图书榜单页
用于断网 / 合规演示，保证爬虫在任何环境都能跑通。

启动: python mock_site/serve.py --port 9000
访问: http://127.0.0.1:9000/top250?start=0
"""
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    """把 /top250 路径映射到 books.html（演示分页 URL 结构）"""

    def translate_path(self, path: str) -> str:
        if path.startswith("/top250"):
            return str(SITE_DIR / "books.html")
        return super().translate_path(path)


def main():
    parser = argparse.ArgumentParser(description="本地演示站点")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"演示站点已启动: http://127.0.0.1:{args.port}/top250?start=0")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n演示站点已停止")
        server.server_close()


if __name__ == "__main__":
    main()
