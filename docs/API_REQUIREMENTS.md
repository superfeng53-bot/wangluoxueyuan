# API Requirements — 成都职业培训网络学院

> **B — 公需年度型**（`site_profile: B`）  
> 用户目标：在「我的培训」按目标年度学习公需科目课程。

## Site profile

- **B — 公需年度型**（API 为 `api.cdwork.cn` JSON，非凉山 HTML 解析）

## Mandatory

- Login / session continuity（Phase 1：`user_token` + `get_userByToken`）
- Account / profile info（`get_userByToken`、`query_user`）
- Yearly train catalog（`GET /train/train/my_train` → 按 `trainTitle` 解析年度）
- Per-year course list + completion check（`train_resource_list` + `my_train.progress/state`）
- Course detail and status（培训详情 `query_train`、章节 `state`/`progress`）
- Course progress reporting（`POST /train/course/start_learning`；播放页可能辅以 WebSocket）
- Course exam, if present（`GET /train/exam/my_exam_list` 等；测试账号当前 0 条考试，公需培训包内未见考试资源 type）

## Optional Selected

- （无）

## Optional Not Selected（B 型默认）

- 学科列表 / 分类列表
- 注册
- 购卡 / 充值
- Credit application（申请学分）

## Site-Specific Notes

- API 基址：`https://api.cdwork.cn`；公共 query：`token`、`device=2`、`hierarchy=A1-1-1-1-`
- 年度来源：`my_train` 列表项 `trainTitle` 中的四位年份（如 `2026年度成都市…`）
- 年度完成：`my_train.progress >= 1.0` 或 `state == 3`（已观测）
- 购课策略 `not_purchased_policy`：`fail`（未报名年度不在 `my_train` 列表）
- `report_mode`：标准 / 快速（Phase 4 调上报间隔；默认标准约 15s）
- 学习上报：`start_training` 进入章节 → 循环 `start_learning` 递增 `studyLength`
- 证书/达标：以培训记录进度为准；`query_userinfo_progress` 为账号级辅助字段

## Phase 2 Domain Plan

- member
- train（my_train + query_train + train_resource_list + year helpers）
- study（start_training + start_learning）
- exam（my_exam_list + query_exam；测试账号无待考，保留接口）
- year_task（`run_year_task` 流水线骨架）
- ~~credit~~（不实现）
- ~~subject list~~（不实现）

## Explicit Skips（B 型默认）

| Capability | Reason | User confirmed |
|------------|--------|----------------|
| 学科列表 / 分类列表 | B 型按年取培训包 | yes |
| Credit application | 达标以培训进度/证书为准 | yes |
| course_planner | 无学科匹配 | yes |
| apply_queue / waiting_apply | 无申请流程 | yes |
| MAX_LEARN_PER_DAY | 公需无单日学习上限 | yes |
