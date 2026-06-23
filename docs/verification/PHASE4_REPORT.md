# Phase 4 Verification Report — WLXY（B 型公需年度）

> 站点：成都职业培训网络学院 · `site_profile: B`

## Definition of Done（B 型 YearTaskRunner）

| 项 | 状态 | 证据 |
|---|---|---|
| `year_task.py` 暴露 `run_year_task` | pass | `wlxy_api/year_task.py` |
| `run_year.py`：`--cookies` + `--years` 按序执行 | pass | `python3 run_year.py --account data/account.json --years 2025,2026 --dry-run` exit 0 |
| 每年：待学章节 → 串行 `study_chapter` → 考试检查 | pass | `--max-chapters 1` 冒烟；`exam` log=`site has no exam flow` |
| 完成探针：`my_train.progress>=1` 或 `state==3` | pass | 2025 `skipped=true, year_completed=true` |
| **进度门禁** `probe_progress` ~60s | pass | 见下方探针记录 |
| 断点续学（重跑从服务端进度继续） | pass | `study_chapter` 同步 `studyLength` + `chapter.study_seconds`；重跑不重复已完成年度 |
| Phase 3 会话重试 | pass | `run_year_task_with_retry` / `probe_progress_with_retry` + `ensure_session_with_member_probe` |
| `--account --auto-login` | pass | `run_year.py --account data/account.json` 写回 `data/cookies.json` |
| 不生成 `course_planner` / 学科映射 | pass | 未新增相关文件 |

## 进度探针（Step 0 硬门禁）

```bash
python3 run_year.py --account data/account.json --years 2026 --probe-progress --probe-seconds 60
```

| 字段 | 值 |
|---|---|
| `ok` | `true` |
| `chapter_id` | `1780647483392197` |
| `study_seconds_before` | `163`（列表 `progress=0.06`） |
| `study_seconds_after` | `179`（响应 `data.studyLength`） |
| `delta` | `16` |

## 冒烟测试摘要

| Step | 命令 | 结果 |
|---|---|---|
| 0 探针 | `--probe-progress` | pass，`delta=16` |
| 1 限章学习 | `--max-chapters 1 --max-reports 2 --report-mode fast` | pass，`chapters_done=1` |
| 2 重复执行 | 同上 | pass，幂等处理同一首章 |
| 3 删 cookies 重登 | `mv cookies.json` → `--probe-progress` | pass，自动登录后探针通过 |
| 4 已完成年度 | `--years 2025,2026 --dry-run` | 2025 `skipped`，2026 待学 48 章 |
| 5 申请学分 | N/A | B 型 Explicit Skip，CLI 无 `--apply-credit` |

## 备注

- 单章时长约 2724s（≈45min），全量 48 章未在冒烟中跑完；生产由 Phase 5 调度器长时间运行。
- **页面可见进度**须走 `POST /train/socket/start_learning_socket`（`authCode=Z`，每 20s）；仅 `start_learning` 不会让课表 progress 变化。
- socket 接口 body **不可**含 `device`/`hierarchy`（否则 `code:512`）。
- 探针/续播以课表 `train_resource_list` 的 `progress` 为准。

## 修复记录（用户反馈页面上无进度）

| 问题 | 根因 | 修复 |
|---|---|---|
| 页面进度不变 | 只用了 `start_learning`，未调 `start_learning_socket` | `study.py` 改为 socket 上报 |
| 探针误报 pass | 用响应 `studyLength` 而非课表 | 探针改读列表 `progress` |

## 刻意跳过

| 项 | 原因 |
|---|---|
| 整年全章节跑完 | 墙钟 >20h，留 Phase 5 常驻服务验证 |
| 考试交卷 | 测试账号 `my_exam_list` 为空 |
