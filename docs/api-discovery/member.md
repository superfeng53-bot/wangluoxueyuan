# API Discovery — member

## Endpoints

### GET `/user/user/get_userByToken`

- Params: `token`, `device`, `hierarchy`
- Success: `success: true`, `code: 0`, `data` 含 `userId`, `name`, `phone`, `token`, `isAuth`
- Failure: `code: 401`, `msg: token验证过期,请重新登录!`

### GET `/user/user/query_user`

- 同 token 参数；返回用户详情（Phase 2 作 profile 补充）

### GET `/user/edu/query_userinfo_progress`

- Params: `userId`（必填）
- Success data 示例: `{"authState": 5, "progress": 0.5}`
- 用途：账号级实人认证/进度辅助；**非**按年证书列表
