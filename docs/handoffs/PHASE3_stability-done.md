# Phase 3 Handoff — WLXY 稳定性层

## 已完成

- `wlxy_api/captcha_limiter.py` — 跨进程冷却（`data/captcha-state.json`）
- `wlxy_api/session_manager.py` — token 复用、`ensure_session`、per-username 锁、`relogin_user`
- `wlxy_api/session_retry.py` — `call_with_session_retry`（业务失效重登 1 次）
- `wlxy_api/responses.py` — `is_session_expired` / `SessionExpiredError`
- `wlxy_api/client.py` — `api_form_post_safe`、`json_post_safe`、`form_get_html` 等

## 关键约定

| 项 | 值 |
|---|---|
| `site_profile` | B（公需年度） |
| `<pkg>` | `wlxy_api` |
| Token 键 | `user_token` |
| Probe | `MemberService.get_profile_by_token()` |
| 无验证码 | `captcha.py` 为 `NoCaptchaRequired`；limiter 仅防频率 |

## Phase 4 入口

1. 复制 `templates/code/runner/course_runner.py` → 调整为 `YearTaskRunner`（B 型已有 `year_task.py` 骨架）
2. 实现 `run_course.py` / `course_runner` 对接 `study.start_learning` 循环
3. `session_retry` 注入学习流水线

## 验收

`docs/verification/PHASE3_REPORT.md` — 全部 DoD `pass`。

## 测试账号

`data/account.json`（gitignored）；cookies 在 `data/cookies.json`。
