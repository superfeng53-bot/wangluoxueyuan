# Phase 5 Handoff — WLXY 多账号常驻服务

## 已完成

| 模块 | 路径 |
|---|---|
| 配置 | `wlxy_svc/config.py`（B 型，`SITE_PROFILE=B`） |
| 持久层 | `wlxy_svc/persistence/store.py` |
| 调度器 | `wlxy_svc/orchestrator.py` |
| Worker | `wlxy_svc/worker.py` + `worker_base.py` |
| 运行时 | `wlxy_svc/runtime.py` |
| Web API | `wlxy_svc/web/app.py` |
| Excel | `wlxy_svc/web/excel_io.py` |
| 控制台 | `wlxy_svc/web/templates/index.html` |
| 入口 | `run_service.py` |

## 关键约定

| 项 | 值 |
|---|---|
| `site_profile` | B |
| 平台中文名 | 成都职业培训网络学院 |
| 默认端口 | 17865（占用则递增） |
| 并发上限 | 400（KV 可调） |
| 凭证模式 | split |
| 跳过 | apply_worker、scheduling、学科/购卡 UI |

## Worker 行为

- `run_once` → `ensure_session`（member probe）→ 按 `target_years_json` 顺序 `YearTaskRunner.run_year_task`
- `extra` 跟踪：`year_status`、`current_year`、`report_mode`、`phase`
- 重学保留 `cookies`/`report_mode`，清除 `year_status`/`phase`/runs

## Phase 6 入口

1. `start.sh` 一键启动
2. `build.sh` + PyInstaller 单文件 `{平台}_{月}_{日}`
3. `scripts/smoke_frozen.py` 打包产物验收

## 启动

```bash
python3 run_service.py
# 或
python3 run_service.py --no-browser --port 17865
```
