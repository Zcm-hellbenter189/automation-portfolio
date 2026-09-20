"""GIL 演示：CPU 密集型 vs I/O 密集型，串行 / 多线程 / 多进程 三种方式对比

目的（亲眼看到 GIL 的作用，而不是靠背结论）：
  实验 1 · CPU 密集型（纯 Python 计算，全程持有 GIL）
      预期：多线程几乎不提速；多进程接近线性提速
  实验 2 · I/O 密集型（HTTP 请求，等待期间释放 GIL）
      预期：多线程就能接近线性提速

用法（在 01-api-test-framework 目录下执行）:
  ..\\.venv\\Scripts\\python.exe perf/gil_demo.py            # 全跑（I/O 实验需要 Mock 服务在跑）
  ..\\.venv\\Scripts\\python.exe perf/gil_demo.py --cpu-only # 只跑 CPU 实验（不需要任何服务）
  ..\\.venv\\Scripts\\python.exe perf/gil_demo.py --base-url http://127.0.0.1:8000

实现说明（这三条是写"并发脚本"的通用注意点）：
  - 被并发执行的函数必须是【顶层函数】：多进程要把它 pickle 到子进程，嵌套函数/闭包不行；
  - Windows 上多进程【必须】有 if __name__ == "__main__" 保护，
    否则子进程 import 本模块时会再次执行 main()，导致无限重启；
  - 统一用 concurrent.futures 的线程/进程池，接口一致、代码量小。
"""
import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
CPU_N = 8_000_000   # 单次 CPU 任务的循环次数
TASK_COUNT = 4      # 每种执行方式各跑几个任务


# ---------- 被并发执行的两个任务 ----------
def cpu_task(n: int) -> int:
    """CPU 密集型：纯 Python 循环 —— 执行期间一直持有 GIL"""
    total = 0
    for i in range(n):
        total += i * i
    return total


def io_task(url: str) -> int:
    """I/O 密集型：HTTP 请求 —— 等待响应期间会释放 GIL"""
    return requests.get(url, timeout=30).status_code


# ---------- 三种执行方式（只关心耗时，不关心返回值） ----------
def run_serial(fn, args):
    start = time.perf_counter()
    for a in args:
        fn(a)
    return time.perf_counter() - start


def run_threads(fn, args, workers):
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fn, args))
    return time.perf_counter() - start


def run_processes(fn, args, workers):
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fn, args))
    return time.perf_counter() - start


def show(label, seconds, base):
    """打印一行结果：耗时 + 相对串行的加速比 + 条形图"""
    speedup = base / seconds if seconds else 0.0
    bar = "#" * min(int(round(speedup * 10)), 40)
    print(f"  {label:<14}{seconds:7.2f}s   加速比 {speedup:5.2f}x   {bar}")


def experiment(title, subtitle, fn, args, workers, conclusion):
    print(f"\n{'=' * 72}")
    print(title)
    print(subtitle)
    print("-" * 72)
    serial = run_serial(fn, args)
    show("串行", serial, serial)
    show(f"{workers} 线程", run_threads(fn, args, workers), serial)
    show(f"{workers} 进程", run_processes(fn, args, workers), serial)
    print(f"\n  → 结论：{conclusion}")


def main():
    parser = argparse.ArgumentParser(description="GIL 演示：CPU 密集 vs I/O 密集")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Mock 服务地址（默认 {DEFAULT_BASE_URL}）")
    parser.add_argument("--tasks", type=int, default=TASK_COUNT,
                        help=f"每种方式执行几个任务（默认 {TASK_COUNT}）")
    parser.add_argument("--cpu-n", type=int, default=CPU_N,
                        help=f"CPU 任务的循环次数（默认 {CPU_N:,}）")
    parser.add_argument("--cpu-only", action="store_true",
                        help="只跑 CPU 实验（不需要 Mock 服务）")
    args = parser.parse_args()

    cores = os.cpu_count() or 1
    workers = min(4, cores)     # 4 核及以上用 4，否则按实际核数

    print("=" * 72)
    print("GIL 演示：为什么 CPU 密集任务多线程无效，而 I/O 密集任务多线程有效")
    print("=" * 72)
    print(f"  本机 CPU 核数   : {cores}")
    print(f"  并发度（workers）: {workers}")
    print(f"  每种方式任务数  : {args.tasks}")
    if workers < 4:
        print(f"  提示：本机只有 {cores} 核，多进程的加速比上限就是核数，属正常现象")

    experiment(
        "实验 1 · CPU 密集型（纯 Python 计算，全程持有 GIL）",
        f"每个任务循环 {args.cpu_n:,} 次乘加",
        cpu_task,
        [args.cpu_n] * args.tasks,
        workers,
        "多线程几乎无提速 —— 同一进程内同一时刻只有一个线程能执行字节码；"
        "多进程接近线性提速 —— 每个进程有独立的 GIL。",
    )

    if args.cpu_only:
        print("\n  （--cpu-only：已跳过 I/O 实验）")
        return

    # 探测服务是否可达：打一个"很快且允许未鉴权"的接口（401 也说明服务活着），
    # 刻意不用 /api/slow —— 探测本身不该再等 3 秒
    try:
        requests.get(f"{args.base_url}/api/users", timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"\n[!] 无法访问 {args.base_url}：{e}")
        print("    I/O 实验需要 Mock 服务在跑。另开一个终端执行：")
        print("        python mock_server.py --port 8000")
        return

    experiment(
        "实验 2 · I/O 密集型（HTTP 请求 /api/slow，服务端固定 sleep 3 秒）",
        "每个请求需要等待服务端 3 秒（等待期间不占用 GIL）",
        io_task,
        [f"{args.base_url}/api/slow"] * args.tasks,
        workers,
        "多线程就能接近线性提速 —— 等 I/O 时会释放 GIL，其他线程可以继续干活；"
        "多进程也有效，但进程创建开销更大。",
    )


if __name__ == "__main__":
    main()
