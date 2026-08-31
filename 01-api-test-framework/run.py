"""一键运行入口：启动 Mock 服务 → 运行 pytest → 输出报告路径

用法: python run.py
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MOCK_PORT = 8000
MOCK_SCRIPT = BASE_DIR / "mock_server.py"
REPORT = BASE_DIR / "reports" / "report.html"


def wait_port(port: int, timeout: float = 10) -> bool:
    """等待端口就绪"""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> int:
    print("=" * 56)
    print("  接口自动化测试框架 - 一键运行")
    print("=" * 56)

    python = sys.executable
    mock = subprocess.Popen(
        [python, str(MOCK_SCRIPT), "--port", str(MOCK_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_port(MOCK_PORT):
            print(f"[!] Mock 服务启动失败（端口 {MOCK_PORT} 可能被占用）")
            return 1
        print(f"[*] Mock 服务已启动: http://127.0.0.1:{MOCK_PORT}")

        cmd = [
            python, "-m", "pytest", "testcases",
            "--html=reports/report.html", "--self-contained-html", "-q",
        ]
        print("[*] 开始执行测试用例 ...\n")
        code = subprocess.call(cmd, cwd=BASE_DIR)

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
