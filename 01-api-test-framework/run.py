"""一键运行入口：启动 Mock 服务 → 运行 pytest → 输出报告路径

用法: python run.py [--port 8000]

改进说明:
  - 支持 --port 手动指定端口（默认 8000），不再写死常量；
  - 端口被占用时自动向后探测空闲端口继续运行（原实现只能报错退出）；
  - 通过 BASE_URL 环境变量把实际端口透传给 pytest 的 client 夹具
    （config/loader.py 已支持该覆盖），用例无需感知端口变化。
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8000
MOCK_SCRIPT = BASE_DIR / "mock_server.py"
REPORT = BASE_DIR / "reports" / "report.html"


def is_port_open(port: int) -> bool:
    """端口是否已被监听（已占用返回 True）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start: int, attempts: int = 20) -> int:
    """从 start 向后探测第一个空闲端口"""
    for port in range(start, start + attempts):
        if not is_port_open(port):
            return port
    raise RuntimeError(f"端口 {start}~{start + attempts - 1} 均被占用，无法启动 Mock 服务")


def wait_port(port: int, timeout: float = 10) -> bool:
    """等待端口就绪"""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            return True
        time.sleep(0.3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="接口自动化测试框架 - 一键运行")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Mock 服务端口（默认 {DEFAULT_PORT}）")
    args = parser.parse_args()

    print("=" * 56)
    print("  接口自动化测试框架 - 一键运行")
    print("=" * 56)

    if is_port_open(args.port):
        # 目标端口被占用：自动换空闲端口，而不是直接失败
        try:
            port = find_free_port(args.port)
        except RuntimeError as e:
            print(f"[!] {e}")
            return 1
        print(f"[!] 端口 {args.port} 已被占用，自动改用端口 {port}")
    else:
        port = args.port

    python = sys.executable
    mock = subprocess.Popen(
        [python, str(MOCK_SCRIPT), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_port(port):
            print(f"[!] Mock 服务启动失败（端口 {port} 可能被占用）")
            return 1
        print(f"[*] Mock 服务已启动: http://127.0.0.1:{port}")

        cmd = [
            python, "-m", "pytest", "testcases",
            "--html=reports/report.html", "--self-contained-html", "-q",
        ]
        # 把实际端口透传给 client 夹具（BASE_URL 覆盖），保证端口自动切换时用例仍指向本服务
        env = dict(os.environ)
        env["BASE_URL"] = f"http://127.0.0.1:{port}"
        print("[*] 开始执行测试用例 ...\n")
        code = subprocess.call(cmd, cwd=BASE_DIR, env=env)

        print(f"\n[*] pytest 退出码: {code}")
        if REPORT.exists():
            print(f"[*] 测试报告已生成: {REPORT}")
        return code
    finally:
        mock.terminate()
        mock.wait()
        print("[*] Mock 服务已关闭")


if __name__ == "__main__":
    sys.exit(main())
