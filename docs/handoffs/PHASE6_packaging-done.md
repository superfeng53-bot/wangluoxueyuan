# Phase 6 Handoff — 打包与一键启动完成

## 状态

Phase 6 **完成**。项目可交付给非开发人员使用。

## 新增/变更文件

| 文件 | 说明 |
|------|------|
| `start.bat` / `start.sh` | 一键启动（自动 venv + pip + run_service） |
| `build.bat` / `build.sh` | 一键打包（`.build-venv` + PyInstaller + smoke） |
| `scripts/build.py` | 生成 spec、构建 `网络学院_<MM>_<DD>.exe`、自动 smoke |
| `scripts/wlxy.spec.template` | PyInstaller onefile 模板 |
| `scripts/smoke_frozen.py` | 隔离目录打包验收（**权威门禁**） |
| `requirements-build.txt` | `pyinstaller>=6.0` |
| `pyproject.toml` | 项目元数据 + ruff |
| `.github/workflows/ci.yml` | ruff + import smoke |
| `data/.gitkeep` | 空 data 目录占位 |
| `README.md` | 一键启动 / 打包 / 目录结构 |

## 代码修补（为通过 frozen smoke）

- `requirements.txt`：`python-multipart`、`tzdata`
- `wlxy_svc/web/app.py`：frozen 模板路径 + `FileResponse` 首页
- 若干 ruff 修复（`cli_exam.py`、`session_manager.py`、`year_task.py`、`excel_io.py`）

## 验收命令

```bash
# 开发态
start.bat                    # Windows
./start.sh                   # macOS/Linux

# 打包（含 smoke）
build.bat                    # → dist/网络学院_06_23.exe

# 单独重跑 smoke
python scripts/smoke_frozen.py
```

## 下一动作（用户可选）

1. `git add` + `commit` + `push` 触发 CI
2. 将 `dist/网络学院_06_23.exe` 复制到目标机器抽测
3. 无需 Phase 7 — 六阶段流程已结束
