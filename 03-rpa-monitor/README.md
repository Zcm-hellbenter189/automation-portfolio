# RPA 定时监控 · 采集 + 报表 + 告警

> 完整的自动化闭环：**定时采集 → 异常判定 → Excel 报表 → 分级告警**。
> 企业办公最常见的刚需形态，改配置即可监控任何真实站点。

## 功能特性

- **完整闭环**：采集（collector）→ 判定（detector）→ 报表（reporter）→ 告警（notifier）
- **多目标监控**：一个配置监控多个 URL，支持期望状态码自定义
- **三重异常判定**：非期望状态 / 请求失败 / 响应过慢，外加响应时间环比波动（定时模式生效）
- **Excel 三页报表**：监控概览 + 采样明细 + 告警记录，带格式可直接交付
- **历史追溯**：SQLite 持久化每次采样，环比分析有据可依
- **告警不骚扰**：默认写日志 + 报表告警页；SMTP 邮件默认关闭，填入配置才启用
- **跨平台定时**：APScheduler 实现，Windows 无需 cron，可注册任务计划程序自启
- **双入口**：`main.py` 单次运行（演示/手动触发），`run_scheduled.py` 常驻定时
- **自带演示服务**：模拟健康/慢响应/异常三种接口，断网也能完整演示告警闭环

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1. 单次运行（自动起演示服务，触发慢响应/500 告警）
python main.py

# 2. 常驻定时（每 60 秒跑一次，Ctrl+C 停止）
python run_scheduled.py
```

接入真实监控：编辑 `config/config.yaml` 的 `targets`，把 URL 换成真实站点即可；如需邮件告警，填 `alert.smtp` 并置 `enabled: true`。

## 运行效果

```
INFO | collector | 健康检查接口: status=200 elapsed=0.01s error=-
INFO | collector | 慢响应接口: status=200 elapsed=3.00s error=-
INFO | collector | 异常接口(500): status=500 elapsed=0.01s error=状态码 500 != 期望 200
WARNING | rpa_monitor | 异常判定: 慢响应接口 -> 响应过慢: 3.0s > 2.0s
WARNING | rpa_monitor | 异常判定: 异常接口(500) -> 状态码 500 != 期望 200
ERROR | notifier | [告警] 慢响应接口 | 响应过慢: 3.0s > 2.0s
ERROR | notifier | [告警] 异常接口(500) | 状态码 500 != 期望 200
INFO | rpa_monitor | 本次监控完成: 3 个目标, 2 个异常
INFO | rpa_monitor | 报表已生成: ...\reports\监控报表_xxx.xlsx
```

## 目录结构

```
03-rpa-monitor/
├── main.py               单次运行入口（自动起演示服务）
├── run_scheduled.py      常驻定时入口（APScheduler）
├── demo_server.py        演示目标服务（纯标准库，模拟健康/慢/异常接口）
├── config/config.yaml    监控目标 / 阈值 / 调度 / 邮件配置
├── monitor/
│   ├── collector.py      指标采集（状态码 + 响应时间）
│   ├── detector.py       异常判定（状态/超时/环比波动）
│   ├── history.py        SQLite 历史采样（环比依据）
│   ├── reporter.py       Excel 三页报表
│   └── notifier.py       告警（日志 + 可选 SMTP 邮件）
├── scheduler/scheduler.py  APScheduler 跨平台调度
├── data/                 运行产物：monitor.db
├── reports/              运行产物：Excel 报表
└── logs/                 运行日志
```

## Windows 开机自启（可选）

1. 打开「任务计划程序」→ 创建基本任务
2. 触发器选「计算机启动时」
3. 操作选「启动程序」，程序填 `.venv\Scripts\pythonw.exe`（无窗口），参数填 `run_scheduled.py`，起始于填本项目路径

## 简历亮点写法

> 实现 RPA 定时监控系统：requests 采集多目标状态码与响应耗时，基于阈值与环比波动规则自动判定异常；openpyxl 生成概览/明细/告警三页 Excel 报表，SQLite 持久化历史采样；APScheduler 实现跨平台定时调度，告警支持日志与可选 SMTP 邮件，形成「采集→判定→报表→告警」完整自动化闭环。
