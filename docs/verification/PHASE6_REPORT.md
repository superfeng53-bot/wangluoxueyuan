# Phase 6 Verification Report — WLXY（网络学院）

> 站点：成都职业培训网络学院 · `site_profile: B`  
> 构建日：2026-06-23

## Definition of Done

| 项 | 状态 | 证据 |
|---|---|---|
| `start.sh` / `start.bat` 一键启动（venv + deps + run_service） | pass | `start.bat` / `start.sh` 已创建；`pip install -r requirements.txt` 后 `python run_service.py` 可起服 |
| `run_service.py` 单实例、二次启动开 WebUI、端口避让、frozen 顶层 except | pass | Phase 5 已验收；`run_service.py` L128-138 frozen `input()` |
| `build.sh` / `build.bat` → 单文件 `网络学院_<MM>_<DD>.exe` | pass | `dist/网络学院_06_23.exe`（~58MB） |
| PyInstaller onefile：`ddddocr` ONNX、模板、uvicorn hiddenimports | pass | `scripts/wlxy.spec.template` 含 `collect_data_files('ddddocr'/'tzdata')`、模板 datas、uvicorn hiddenimports |
| `console=True` 保留终端 | pass | spec `console=True` |
| `scripts/smoke_frozen.py` 存在且 build 后自动调用 | pass | `build.py` L41-46 `check_call(smoke)` |
| 隔离目录 smoke：`/api/health`、`/`、`/api/config` 200；`.run/`、`data/` 在 exe 旁 | pass | 见下方 smoke 输出 |
| 二次双击 exe 只开浏览器 | pass | `SingleInstanceLock` + `open_existing_ui`（Phase 5 逻辑，frozen 同代码路径） |
| `.github/workflows/ci.yml` lint + import smoke | pass | `.github/workflows/ci.yml`；本地 `ruff check .` + import 均 exit 0 |
| `README.md` 含安装/运行/打包/目录 | pass | `README.md` 已更新 |
| `pyproject.toml` 依赖与元数据 | pass | `pyproject.toml` |

## 打包 Smoke 记录

```text
[smoke] 复制到隔离目录: C:\Users\15712\AppData\Local\Temp\frozen-smoke-ihiikpdb
[smoke] 服务已监听: http://127.0.0.1:54620
[smoke] GET /api/health → OK
[smoke] GET /api/config → OK
[smoke] GET / → OK
[smoke] 存在: .run/service/service.lock
[smoke] 存在: data
[smoke] PASS — 打包产物在隔离目录运行正常
```

命令：`.\build-venv\Scripts\python.exe scripts\build.py --clean`（经 `.build-venv`）

## 打包修复项（本次）

| 问题 | 修复 |
|------|------|
| 缺 `python-multipart` | 加入 `requirements.txt` / spec hiddenimports |
| 缺 `tzdata`（`Asia/Shanghai`） | 加入依赖 + `collect_data_files('tzdata')` |
| frozen 下 `GET /` 500（Jinja2 模板路径） | `app.py` `_resolve_templates_dir()` + `FileResponse` |
| spec 入口路径 | `../run_service.py` + `pathex=['..']` |
| CI ruff | 补 `app.py` credential 导入；清理未使用 import |

## 交付物

- 开发启动：双击 `start.bat` 或 `./start.sh`
- 单文件分发：`dist/网络学院_06_23.exe`（复制到任意目录即可运行，同目录生成 `data/`、`.run/`）
- 打包验收重跑：`python scripts/smoke_frozen.py`

## 备注

- CI 在 GitHub push 后需远端跑绿（本地 import + ruff 已通过）。
- macOS 未签名二进制需 `xattr -d com.apple.quarantine <binary>`（见 phase6 文档）。
