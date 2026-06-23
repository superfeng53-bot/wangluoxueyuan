# Phase 1 Handoff — 成都职业培训网络学院

## 已完成

- 项目脚手架：`wlxy_api` / `wlxy_svc`，根目录 `/Users/fengsuper/Desktop/网络学院`
- 浏览器侦察：首页弹窗登录，无验证码
- 纯 HTTP 登录 + 会话检查实现并验证

## 关键路径（绝对路径）

- 项目根：`/Users/fengsuper/Desktop/网络学院`
- 登录文档：`docs/LOGIN_FLOW.md`
- 工具包：`wlxy_api/`
- 账号：`data/account.json`（gitignore）
- Cookies：`data/cookies.json`

## 站点决策（不可丢）

- captcha 族：**无**
- `<pkg>` / `<svc>`：`wlxy_api` / `wlxy_svc`
- **site_profile：B** — 公需科目按年度，页面 `/pages/mine/mytrain/list`
- 密码：MD5 大写；会话：`localStorage.user_token` → `cookies.json`
- API 基址：`https://api.cdwork.cn`；公共参数 `device=2`, `hierarchy=A1-1-1-1-`
- 用户目标：学习「我的培训」中选择年份的公需课程

## 已验证命令

```bash
cd /Users/fengsuper/Desktop/网络学院
python3 -m wlxy_api.cli_login
python3 -m wlxy_api.cli_login --check
```

## 验收摘要

- 报告：`docs/verification/PHASE1_REPORT.md`
- 缺口：无（`docs/gaps/` 无文件）

## 未完成 / 下步第一件事

1. Phase 2：确认 B 型 `docs/API_REQUIREMENTS.md`（复制 `api-requirements-b.md`）
2. 浏览器走一遍：我的培训 → 进入年度课程 → 视频/考试 API 抓包
3. 实现 `train` / `course` / `study` Service

## 新对话启动语（复制给 Agent）

请继续 learning-site-automation skill，从 Phase 2 开始。先 Read：
- docs/handoffs/PHASE1_login-recon-done.md
- phase2-api-tools.md
- site-profiles.md（B 型）
项目根：/Users/fengsuper/Desktop/网络学院
站点：成都职业培训网络学院 wlxy.org.cn，B 型公需按年学习。
