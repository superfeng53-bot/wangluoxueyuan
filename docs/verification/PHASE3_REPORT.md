# Phase 3 Verification Report

## Definition of Done

| Item | Status | Evidence |
|------|--------|----------|
| `SessionManager` 按 `user_id` 隔离 `HttpClient` | pass | `wlxy_api/session_manager.py` → `get_client` / `remove` |
| `ensure_session` 返回 `(reused_token, cookies, user_info, error)` 且 probe 成功时跳过登录 | pass | `ensure_session_with_member_probe` 5/5 复用 token（`get_userByToken` probe） |
| `captcha_limiter` 全局冷却 + 最小间隔 + 识别失败退避 | pass | 3 次 `mark_captcha_attempt`+`wait_before_captcha` 间隔 3.61s；连续 3 次失败触发 90s 冷却 |
| `client.py` 安全重试（写 3 次 / 读 4 次，指数退避，4xx 不重试） | pass | `api_form_post_safe` / `json_post_safe` / `form_post_safe` / `api_get_safe` / `form_get_html` |
| 登录重试与业务重试分离 | pass | 登录走 `LoginService`+`captcha_limiter`；业务走 `session_retry.call_with_session_retry` + `is_session_expired` |
| `responses.is_session_expired` 供全局使用 | pass | `require_data` 对 code 401 抛 `SessionExpiredError`；`session_retry` 导入同一 helper |

## Smoke commands

```bash
# Token 复用 + captcha 间隔 + session_retry（内联脚本 exit 0）
python3 - <<'PY' ...  # 见会话记录，TOKEN_REUSE 5/5

# 现有 CLI 仍可用
python3 -m wlxy_api.cli_member profile
python3 -m wlxy_api.cli_login --check
```

## Files added/changed

| File | Change |
|------|--------|
| `wlxy_api/captcha_limiter.py` | **新增** — 冷却状态持久化（`data/captcha-state.json`） |
| `wlxy_api/session_manager.py` | **增强** — `ensure_session`、per-username 锁、冷却感知登录、`relogin_user` |
| `wlxy_api/session_retry.py` | **新增** — 业务一次重登重试 |
| `wlxy_api/responses.py` | **增强** — `SessionExpiredError`、`is_session_expired` |
| `wlxy_api/client.py` | **增强** — `*_safe` 重试族、`form_get_html`、4xx 跳过重试 |
| `wlxy_api/login.py` | **增强** — `api_form_post_safe`、频率限制检测 |
| `wlxy_api/__init__.py` | **增强** — 启动时 `configure_state_file` |

## Site notes

- 本站**无图形验证码**；`captcha_limiter` 仍用于登录频率保护与 Phase 5 UI 冷却展示。
- 最便宜 probe：`GET /user/user/get_userByToken`（`ensure_session_with_member_probe`）。

## Gaps

无未关闭缺口。
