# API Discovery — exam

## 侦察结论

测试账号「我的考试」为空；2025 已完成公需培训的 `train_resource_list` 仅含 `type: "1"` 视频课，未见考试资源。

## Endpoints（平台存在，公需账号当前无待考）

### GET `/train/exam/my_exam_list`

- Params: `type`（1=未考, 2=已考）, `pageNum`, `pageSize`
- Success: `data.data.result[]`, `examCount`

### GET `/train/exam/query_exam`

- Params: `examId`
- 无效 id: `code: 3353`, `msg: 该资源已被下线或删除!`

### POST 类考试提交

- 路径待有真实 `examId` 时补全（`submit_exam_answer` 等返回 500/405，需有效试卷）

## Phase 2 处理

- 实现 `ExamService` 封装已确认 GET；交卷方法留桩，Phase 4 有试卷样本再补
