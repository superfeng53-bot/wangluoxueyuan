# Phase 4 Handoff — WLXY 单账号年度 Runner

## 已完成

- `wlxy_api/year_task.py` — `YearTaskRunner`：`probe_progress`、`run_year_task`、`*_with_retry`
- `wlxy_api/study.py` — 断点续学、`probe_chapter_progress`、响应 `studyLength` 同步、先 sleep 再上报
- `wlxy_api/train.py` — `TrainChapter.study_seconds`、`find_chapter`
- `wlxy_api/session_manager.py` — `get_year_task_runner`
- `run_year.py` — B 型 CLI（`--years`、`--probe-progress`、`--dry-run`、`--max-chapters`）
- `run_course.py` — 重定向提示至 `run_year.py`

## 关键约定

| 项 | 值 |
|---|---|
| `site_profile` | B |
| 目标年度（测试账号） | 2026 待学（48 章），2025 已完成 |
| 上报间隔 | normal=15s，fast=3s（服务端仍以墙钟为准） |
| 进度门禁 | `probe_progress` delta≥1，用响应 `studyLength` |
| 考试 | 无待考；`exam_cleared=true` |

## Phase 5 入口

1. 复制 `templates/code/service/*` → `wlxy_svc/`
2. `worker_base.run_year_pipeline()` 调 `YearTaskRunner.run_year_task_with_retry`
3. `store.py` B 型列：`target_years_json`，无学科/申请队列
4. Web UI §14 年度 pill

## 验收

`docs/verification/PHASE4_REPORT.md` — B 型 DoD 全部 `pass` 或 `skipped` 有记录。
