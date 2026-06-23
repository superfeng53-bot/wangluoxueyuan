# API Discovery — study

## Endpoints

### POST `/train/course/start_learning`

- Body（form）:
  - `trainId`, `trainRecordId`, `courseId`, `courseChapterId`, `chapterId`
  - `studyLength`（上报播放秒数）, `type`（1）, `appId`, `fileId`, `orgId`, `userId`
- Success: `data.res: "success"`, 返回 `url`, `chapterId`, `currentTimes`, `studyLength`
- 仅用于进入章节；**页面可见进度**靠下方 socket 接口

### POST `/train/socket/start_learning_socket`

- **不可**在 body 中附带 `device` / `hierarchy`（会 `code:512 缺失关键参数`）
- Body（form，与前端 XMLHttpRequest 一致）:
  - `token`, `courseChapterId`, `orgId`, `authCode`（固定 `"Z"`）
  - `currentTimes`（当前播放秒数）, `playStatus`（`play` / `pause` / `end`）
- Success: `code: 0`；课表 `train_resource_list` 的章节 `progress` 会更新

## 建议上报节奏

- 与前端播放页一致：进入后 `playStatus=play`，之后每 **20s** socket 上报一次 `currentTimes += 20`
- `orgId` 取自 `start_training` 响应或 `query_train`
