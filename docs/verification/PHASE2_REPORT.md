# Phase 2 Verification Report

## Definition of Done

| Item | Status | Evidence |
|------|--------|----------|
| One `*Service` per business domain | pass | `member.py`, `train.py`, `study.py`, `exam.py`, `year_task.py` |
| One `cli_*.py` per service | pass | `cli_member`, `cli_train`, `cli_study`, `cli_exam`, `cli_year` |
| `API_REFERENCE.md` | pass | `wlxy_api/API_REFERENCE.md` |
| `docs/API_REQUIREMENTS.md` | pass | B 型预填 + 侦察参数 |
| Shared `HttpClient` | pass | 所有 Service 注入 `HttpClient` |
| `ApiResponse` / parsers | pass | `wlxy_api/responses.py` |

## CLI smoke

```bash
python3 -m wlxy_api.cli_member profile          # exit 0
python3 -m wlxy_api.cli_train years               # 2026–2023 四条年度记录
python3 -m wlxy_api.cli_train year 2026 --chapters  # 48 待学章节
python3 -m wlxy_api.cli_exam pending              # [] 
python3 -m wlxy_api.cli_year --year 2026 --dry-run  # 48 pending
```

## Skipped / deferred

| Item | Status | Reason |
|------|--------|--------|
| Exam submit flow | skipped | 测试账号 `my_exam_list` 为空；公需包仅 type=1 视频 |
| WebSocket 学习上报 | skipped | 播放页存在 `wss://api.cdwork.cn/train`；Phase 4 对照真播放再校准 |
| 独立证书列表 API | skipped | 用户证书以 `my_train.progress` 为准；`cert_manage_list` 为公开展示 |

## Site quirks

- 与凉山公需不同：JSON API（`api.cdwork.cn`），非 HTML 解析
- 年度 = `my_train.trainTitle` 中的年份
- 学习：`start_training` + 循环 `start_learning` 递增 `studyLength`
- 2026 公需：12 门课 × 多章节 ≈ 48 待学章节
