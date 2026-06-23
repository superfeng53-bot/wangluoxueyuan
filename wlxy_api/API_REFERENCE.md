# wlxy_api API Reference

成都职业培训网络学院（`api.cdwork.cn`）业务接口。公共 query：`token`、`device=2`、`hierarchy=A1-1-1-1-`。

## MemberService

### get_profile_by_token()

- Endpoint: `GET /user/user/get_userByToken`
- Success: `{ success: true, code: 0, data: { userId, name, phone, token, isAuth, ... } }`
- Failure: `code: 401` → token 失效

### query_userinfo_progress(user_id)

- Endpoint: `GET /user/edu/query_userinfo_progress`
- Params: `userId`
- Response data: `{ authState, progress }`

## TrainService（B 型年度）

### list_yearly_trains()

- Endpoint: `GET /train/train/my_train?state=1&pageNum=&pageSize=`
- 从 `trainTitle` 解析年份，映射为 `YearTrainRecord`
- 完成判据: `progress >= 1.0` 或 `state == 3`

### list_year_chapters(year)

1. `get_year_record(year)` → `trainId`
2. `GET /train/train/train_resource_list?trainId=...`
3. 展开 `type=="1"` 资源的 `listChapter`

### start_training(train_id, train_record_id)

- Endpoint: `POST /train/train/start_training`
- Body: `trainId`, `trainRecordId`
- Sample data: `{ chapterId, courseId, appId, fileId, url, studyLength }`

## StudyService

### begin_chapter_session(record, chapter)

1. `POST /train/train/start_training`（`trainId`, `trainRecordId`）
2. `POST /train/course/start_learning`（`courseId`, `orgId`, `courseChapterId`）
3. 返回 `currentTimes` 作为续播起点

### report_socket_progress(chapter, org_id, current_times, play_status)

- Endpoint: `POST /train/socket/start_learning_socket`
- Body: `token`, `courseChapterId`, `orgId`, `authCode=Z`, `currentTimes`, `playStatus`
- **禁止**附带 `device`/`hierarchy`（使用 `HttpClient.socket_form_post`）
- 每 20s 递增 `currentTimes`；页面课表 `progress` 以此为准

## ExamService

### list_my_exams(exam_type)

- Endpoint: `GET /train/exam/my_exam_list`
- Params: `type`（1 未考 / 2 已考）, `pageNum`, `pageSize`

### query_exam(exam_id)

- Endpoint: `GET /train/exam/query_exam?examId=`
- Failure: `code: 3353` 资源下线

## YearTaskRunner

### probe_progress(year, probe_seconds=60, min_delta=1)

B 型进度门禁：首章待学 → `start_training` → 循环 `start_learning`（先 sleep 再递增）→ 以响应 `data.studyLength` 计算 delta（列表 `progress` 滞后）。

### run_year_task(year, report_mode, dry_run, max_chapters, max_reports_per_chapter)

串行：待学章节 → `study_chapter`（断点续学：列表 `study_seconds` + 服务端 `studyLength` 同步）；若 `my_exam_list` 有待考则中止（公需测试账号当前无考试）。

### run_year_task_with_retry / probe_progress_with_retry

注入 `session_retry.call_with_session_retry`，会话失效自动重登一次。

## CLI

- `python run_year.py --account data/account.json --years 2026 --probe-progress`
- `python run_year.py --account data/account.json --years 2026,2025`
