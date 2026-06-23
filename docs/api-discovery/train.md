# API Discovery — train / course (B 型年度)

## Endpoints

### GET `/train/train/my_train`

- Params: `state`（1=培训中）, `pageNum`, `pageSize`
- Success: `data.data.result[]` 含 `trainId`, `trainRecordId`, `trainTitle`, `progress`, `state`, `length`, `startTime`, `endTime`
- 年度解析：从 `trainTitle` 提取 `20xx`

### GET `/train/train/query_train`

- Params: `trainId`
- 培训详情：标题、时间、机构等

### GET `/train/train/train_resource_list`

- Params: `trainId`, `pageNum`, `pageSize`, `sortBy=true`, `sortField=sort`, `isXcx=0`
- Success: `data.result[]` 课程资源；`type: "1"` 为视频课；`listChapter[]` 含章节进度
- 章节 `state`: 1 未开始, 2 学习中, 3 已完成（观测）

### POST `/train/train/start_training`

- Body: `trainId`, `trainRecordId`
- 进入当前待学章节，返回 `chapterId`, `courseId`, `url` (m3u8), `fileId`, `appId`
