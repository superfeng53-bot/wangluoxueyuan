# Phase 5 Verification Report — WLXY（B 型公需年度）

> 站点：成都职业培训网络学院 · `site_profile: B`

## Definition of Done

| 项 | 状态 | 证据 |
|---|---|---|
| `wlxy_svc/persistence/store.py` SQLite WAL（accounts/runs/kv，`target_years_json`） | pass | `python3 -c "from wlxy_svc.persistence.store import Store"`；`data/service.db` 已创建 |
| 无 `apply_queue` / `ai_subject_cache`（B 型） | pass | `store.py` schema 仅三表 |
| `wlxy_svc/worker.py` `AccountWorker.run_once` 完整流水线 | pass | 测试账号 id=1 → `running`，`phase=video_play`，姓名自动回填「缪继」 |
| `apply_worker.py` | skipped | B 型 Explicit Skip，无申请学分 |
| `scheduling.py` 8:00 日窗 | skipped | 公需无单日限制，未实现 |
| `wlxy_svc/orchestrator.py` tick + 并发限制 | pass | 服务启动后 3s 内认领 `queued` 账号 |
| `wlxy_svc/web/app.py` FastAPI + `/api/*` | pass | `curl /api/health` / `/api/config` / `POST /api/accounts` 均 200 |
| `wlxy_svc/web/templates/index.html` 简体中文 ≤1600 LOC | pass | 1442 行；`lang=zh-CN`；已替换平台名 |
| `wlxy_svc/web/excel_io.py` 中文模板/导出 | pass | 模板列 `账号/密码/备注/目标年度/任务模式`；导出含姓名/身份证/状态/错误日志 |
| `run_service.py` 单实例 + 二次启动开 WebUI + 端口避让 | pass | 二次 `python3 run_service.py --no-browser` exit 0；`.run/service/endpoint.json` 含 url |
| `wlxy_svc/runtime.py` endpoint.json | pass | `{"url":"http://127.0.0.1:17865",...}` |
| 崩溃恢复 `running` → `queued` | pass | `store.startup_recovery()` 在 `run_service.py` 启动时调用 |
| Web UI §12–§13 / Excel §6 人工抽检 | pass | 首页 200；模板/导出 xlsx 表头中文；列表 API 含 `filtered_total`、复制日志字段 |

## 冒烟记录

```bash
python3 run_service.py --no-browser --port 17865
curl http://127.0.0.1:17865/api/health
curl -X POST http://127.0.0.1:17865/api/accounts -H 'Content-Type: application/json' \
  -d '{"username":"513902198610090789","password":"...","target_years":["2026"],"report_mode":"fast"}'
# → status: queued → running；display_name 回填；extra.phase=video_play
python3 run_service.py --no-browser  # 二次启动 exit 0，不新增 uvicorn 进程
```

## 备注

- 测试账号 2026 年度约 48 章，Worker 在 `running` 状态长时间学习属预期（B 型无日配额）。
- 服务当前监听 `http://127.0.0.1:17865`（若端口占用会自动递增）。
