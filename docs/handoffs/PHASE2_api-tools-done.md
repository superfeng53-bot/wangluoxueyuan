# Phase 2 Handoff — 成都职业培训网络学院

## 已完成

- B 型 `docs/API_REQUIREMENTS.md`、`docs/通用需求说明.md`
- API 侦察：`docs/api-discovery/{member,train,study,exam}.md`
- 服务层：`member`, `train`, `study`, `exam`, `year_task`
- CLI：`cli_member`, `cli_train`, `cli_study`, `cli_exam`, `cli_year`
- `wlxy_api/API_REFERENCE.md`

## 关键路径

- 项目根：`/Users/fengsuper/Desktop/网络学院`
- 年度列表：`GET /train/train/my_train`
- 年课表：`GET /train/train/train_resource_list`
- 学习：`POST /train/course/start_learning`
- 画像：**B** — `target_years` + `YearTaskRunner`

## 站点决策（不可丢）

- `site_profile: B`
- 无学科列表、无申请学分
- 考试 API 存在但公需账号当前 0 待考
- 年度完成：`progress>=1` 或 `state==3`

## 已验证命令

```bash
cd /Users/fengsuper/Desktop/网络学院
python3 -m wlxy_api.cli_train years
python3 -m wlxy_api.cli_year --year 2026 --dry-run
```

## 下步（Phase 3）

1. `session_manager` 重试、token 失效重登、`api_form_post_safe`
2. 学习上报 SSL 间歇失败退避
3. Phase 4：`run_course.py` 接 `YearTaskRunner` 真跑 2026

## 新对话启动语

请继续 learning-site-automation Phase 3。先 Read：
- docs/handoffs/PHASE2_api-tools-done.md
- phase3-stability.md
项目根：/Users/fengsuper/Desktop/网络学院
