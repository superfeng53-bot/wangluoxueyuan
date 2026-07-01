# 网络学院

成都职业培训网络学院（https://www.wlxy.org.cn/）自动化学习客户端。B 型公需年度：按目标年度自动刷课、考试、同步学时进度。

## 一键启动

- **Windows**：双击 `start.bat`
- **macOS / Linux**：`./start.sh`

首次运行会自动创建 `.venv` 并安装依赖，随后启动 Web 控制台并打开浏览器。

## 命令行

```bash
pip install -r requirements.txt
python run_service.py
```

常用参数：

- `--no-browser`：不自动打开浏览器
- `--port 17865`：指定起始端口（占用时自动递增）
- `--credential-input-mode split|combined`：凭证输入模式

## 打包

```bash
./build.sh      # macOS / Linux；成功后自动跑 smoke_frozen
build.bat       # Windows
```

产物位于 `dist/网络学院_<月>_<日>.exe`（或 macOS 无扩展名单文件），保留控制台窗口输出日志。

### 打包验收

```bash
python scripts/smoke_frozen.py   # 单独重跑；须 exit 0
```

开发态 `./start.sh` / `python run_service.py` 通过**不能**代替上述命令。

## 目录结构

```
网络学院/
├── wlxy_api/              # HTTP 工具包（登录、验证码、课程/考试 API）
├── wlxy_svc/              # 常驻服务（调度器、Worker、Web 控制台）
│   └── web/templates/     # 简体中文 Web UI
├── docs/                  # 登录流程、API 文档、阶段验收报告
├── data/                  # 本地数据（gitignore，含 service.db）
├── .run/                  # 运行时锁与 endpoint.json（gitignore）
├── run_course.py          # 单账号端到端跑课（Phase 4）
├── run_year.py            # 单账号按年任务
├── run_service.py         # 多账号常驻服务入口
├── start.bat / start.sh   # 一键启动
└── build.bat / build.sh   # 单文件打包
```

## CLI 常用命令

```bash
python -m wlxy_api.cli_login      # 测试登录
python -m wlxy_api.cli_member     # 查询账号信息
python -m wlxy_api.cli_study      # 学习进度
python -m wlxy_api.cli_exam       # 考试相关
python run_year.py                # 单账号年度任务
python run_course.py              # 单账号完整流水线
```

## 免责声明

仅供学习与研究。使用自动化访问第三方平台时请遵守平台条款与法律法规。
