"""成都职业培训网络学院 — 服务级常量（B 型公需年度）。"""
from __future__ import annotations

DEFAULT_CONCURRENCY = 400
MAX_CONCURRENCY = 400
MIN_CONCURRENCY = 1

TICK_SECONDS = 3
TICK_STARTS_PER_SECOND = 10
RETRY_DELAY_SEC = 60
MAX_RETRY = 5

SERVICE_PORT = 17865
SITE_PROFILE = "B"

# B 型：无单日学习/申请配额，不使用 scheduling 日窗
MAX_LEARN_PER_DAY = 0
MAX_APPLY_PER_DAY = 0

PLATFORM_CN = "成都职业培训网络学院"
LOGO_LETTER = "网"

# 凭证输入：split=账号+密码两栏 | combined=一栏粘贴（见 data/account.json）
CREDENTIAL_INPUT_MODE = "split"
