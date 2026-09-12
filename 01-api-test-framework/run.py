"""一键运行入口：启动 Mock 服务 → 运行 pytest → 输出报告路径

用法:
  python run.py                              # 本地日常：起 Mock、跑全部用例、出 HTML 报告
  python run.py --env=test -m "not slow"     # 切环境 + 跳过慢用例，日常提速
  python run.py --ci                         # CI 模式：额外产出 JUnit XML 与 Allure 结果

参数说明:
  --port N      Mock 服务端口（默认 8000，被占用时自动向后探测空闲端口）
  --env NAME    运行环境，取 config/config.yaml 顶层 key（dev/test/prod，默认 dev）
  -m EXPR       pytest marker 表达式（如 "not slow"；不传 = 全量执行，CI 用全量）
  --junitxml    产出 reports/junit.xml（Jenkins 原生用例趋势图，pytest 内置能力）
  --allure      产出 reports/allure-results（需 pip install allure-pytest）
  --ci          等价于 --junitxml --allure，供 Jenkinsfile 调用
  --no-clean    保留上一轮 allure-results（默认每轮先清空，避免新旧结果混杂）

实现说明:
  - 端口被占用时自动向后探测空闲端口继续运行（原实现只能报错退出）；
  - 通过 BASE_URL 环境变量把实际端口透传给 pytest 的 client 夹具
    （config/loader.py 已支持该覆盖），用例无需感知端口变化；
  - 未安装 allure-pytest 时自动降级跳过 Allure 收集并给出提示，不让整条流水线失败；
  - 退出码 = pytest 退出码，非 0 会让 Jenkins 构建变红（持续集成的关键约定）。
"""
import argparse
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8000
MOCK_SCRIPT = BASE_DIR / "mock_server.py"
REPORTS_DIR = BASE_DIR / "reports"
REPORT = REPORTS_DIR / "report.html"
JUNIT_XML = REPORTS_DIR / "junit.xml"
ALLURE_RESULTS = REPORTS_DIR / "allure-results"
ALLURE_REPORT = REPORTS_DIR / "allure-report"


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


def has_module(name: str) -> bool:
    """当前解释器是否可用指定模块（用于判断 allure-pytest 插件是否已安装）

    为什么不用 try/import：find_spec 只查不导入，避免真的 import pytest 插件带来副作用。
    """
    return importlib.util.find_spec(name) is not None


def clean_dir(path: Path) -> None:
    """递归清空目录

    Allure 结果目录是「累积式」的：上一轮的 json 不删，新报告会把旧用例一起渲染进去，
    出现「明明只跑了 15 条却显示 30 条」的诡异现象，所以每轮必须先清空。
    """
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def try_render_allure_report() -> None:
    """本机若装了 allure 命令行（需 Java）就直接渲染 HTML；否则提示由 Jenkins 插件渲染

    allure 命令行 = allure-2.x/bin/allure(.bat)，需要 Java 11+。
    CI 环境不需要它：Jenkins 的 Allure Plugin 会读 allure-results 自己渲染。

    重要：报告渲染只是「锦上添花」，任何失败都必须被吞掉——
    绝不能因为它让整条流水线变红或改变 pytest 的退出码。
    """
    allure_bin = shutil.which("allure")
    if allure_bin is None:
        print("[*] 未检测到 allure 命令行（需 Java），跳过本地 HTML 渲染")
        print("    Jenkins 侧由 Allure 插件自动渲染；本地可先看 reports/report.html")
        return

    print("[*] 正在渲染 Allure 报告 ...")
    cmd = [allure_bin, "generate", str(ALLURE_RESULTS), "-o", str(ALLURE_REPORT), "--clean"]
    # Windows 上 allure 是 .bat 批处理：CreateProcess 不能直接执行 .bat，
    # 必须显式交给 cmd /c（否则报 WinError 2 系统找不到指定的文件）
    if os.name == "nt" and allure_bin.lower().endswith((".bat", ".cmd")):
        cmd = ["cmd", "/c", *cmd]

    try:
        code = subprocess.call(cmd, cwd=BASE_DIR)
    except OSError as e:
        print(f"[!] Allure 渲染失败（已忽略，不影响测试结果）: {e}")
        return

    if code == 0:
        print(f"[*] Allure 报告已生成: {ALLURE_REPORT / 'index.html'}")
    else:
        print(f"[!] Allure 渲染返回非 0（{code}），不影响测试结果")
        print(f"    可手动渲染: allure generate {ALLURE_RESULTS} -o {ALLURE_REPORT} --clean")


def main() -> int:
    parser = argparse.ArgumentParser(description="接口自动化测试框架 - 一键运行")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Mock 服务端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--env", default="dev",
                        help="运行环境，取 config.yaml 顶层 key（默认 dev）")
    parser.add_argument("-m", "--marker", default=None,
                        help='pytest marker 表达式，如 "not slow"（不传 = 全量执行）')
    parser.add_argument("--junitxml", action="store_true",
                        help="产出 reports/junit.xml（供 Jenkins 展示用例明细与趋势）")
    parser.add_argument("--allure", action="store_true",
                        help="产出 reports/allure-results（需 pip install allure-pytest）")
    parser.add_argument("--ci", action="store_true",
                        help="CI 模式：等价于 --junitxml --allure，供 Jenkinsfile 调用")
    parser.add_argument("--no-clean", action="store_true",
                        help="保留上一轮 allure-results（默认每轮先清空，避免新旧结果混杂）")
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
            "--html=reports/report.html", "--self-contained-html",
            "--env", args.env,
            "-q",
        ]

        # 慢用例隔离：日常传 "not slow" 提速；CI 不传 marker，跑全量
        if args.marker:
            cmd += ["-m", args.marker]

        # JUnit XML：pytest 内置能力，Jenkins 用 junit 步骤读取并画通过率趋势图
        want_junit = args.junitxml or args.ci
        if want_junit:
            cmd.append("--junitxml=reports/junit.xml")

        # Allure：装了就收集，没装就降级跳过——不让「报告增强」拖垮整条流水线
        want_allure = args.allure or args.ci
        if want_allure and not args.no_clean:
            clean_dir(ALLURE_RESULTS)
        if want_allure:
            if has_module("allure_pytest"):
                cmd.append("--alluredir=reports/allure-results")
            else:
                print("[!] 未安装 allure-pytest，已跳过 Allure 结果收集")
                print("    安装后启用: pip install allure-pytest")
                want_allure = False

        # 把实际端口透传给 client 夹具（BASE_URL 覆盖），保证端口自动切换时用例仍指向本服务
        env = dict(os.environ)
        env["BASE_URL"] = f"http://127.0.0.1:{port}"
        # Windows 控制台 + CI 日志里的中文/emoji 输出必需，否则报告里是乱码
        env["PYTHONIOENCODING"] = "utf-8"

        print(f"[*] 运行环境: {args.env} | Mock 端口: {port}")
        print("[*] 开始执行测试用例 ...\n")
        code = subprocess.call(cmd, cwd=BASE_DIR, env=env)

        print(f"\n[*] pytest 退出码: {code}")
        if REPORT.exists():
            print(f"[*] HTML 报告  : {REPORT}")
        if want_junit and JUNIT_XML.exists():
            print(f"[*] JUnit XML  : {JUNIT_XML}   <- Jenkins junit 步骤读取")
        if want_allure:
            print(f"[*] Allure 结果: {ALLURE_RESULTS}   <- Jenkins Allure 插件渲染")
            try_render_allure_report()
        return code
    finally:
        mock.terminate()
        mock.wait()
        print("[*] Mock 服务已关闭")


if __name__ == "__main__":
    sys.exit(main())
