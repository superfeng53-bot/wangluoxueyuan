# Phase 1 Verification Report — 成都职业培训网络学院

| DoD 项 | 状态 | 证据 |
|---|---|---|
| `docs/LOGIN_FLOW.md` | pass | 已写入登录端点、MD5 密码、token 会话、会话检查 |
| `<pkg>/captcha.py` | pass | `wlxy_api/captcha.py` — 无验证码，`NoCaptchaRequired` |
| `<pkg>/login.py` `LoginResult` | pass | `wlxy_api/login.py` 返回完整 dataclass |
| `<pkg>/cli_login.py` 写 cookies | pass | `python3 -m wlxy_api.cli_login` → `data/cookies.json` |
| `data/account.json` + gitignore | pass | `data/account.json` 存在；`.gitignore` 含 `data/` |
| 测试账号登录成功 | pass | CLI 输出 `login ok: 缪继`；`--check` → `session_ok` |

## 验证码族

**无验证码**（D 类不适用；纯账号密码，非 SMS/人脸）

## 关键端点

- 登录：`POST https://api.cdwork.cn/user/user/user_login`
- 会话检查：`GET https://api.cdwork.cn/user/user/get_userByToken?token=...`
