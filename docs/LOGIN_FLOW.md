# 成都职业培训网络学院 — 登录流程

站点：https://www.wlxy.org.cn/  
API 域名：`https://api.cdwork.cn`  
画像：**B 型**（公需科目 / 按年度培训，`/pages/mine/mytrain/list`）

## 1. 前端流程

1. 打开首页 `https://www.wlxy.org.cn/`
2. 点击右上角「登录」，弹出登录框（`账号登录` / `统一用户登录`）
3. 在「账号登录」页签填写：
   - 手机号或身份证号（`input.ac`）
   - 密码（`input.pwd`）
4. 勾选「已仔细阅读并同意 用户协议 和 隐私政策」（**必勾**，否则不发起请求）
5. 点击「登录」按钮（`.loginForm .submit`）
6. 前端对明文密码做 **MD5 大写**，`POST` 到 `api.cdwork.cn`
7. 成功后将 `data.token` 写入 `localStorage.user_token`，并更新 Vuex `userInfo`

**无图形验证码、无短信验证码**（账号密码直登）。

## 2. 登录请求

| 项 | 值 |
|---|---|
| Method | `POST` |
| URL | `https://api.cdwork.cn/user/user/user_login` |
| Content-Type | `application/x-www-form-urlencoded` |

### 请求字段

| 字段 | 说明 | 示例 |
|---|---|---|
| `phone` | 手机号或身份证号 | `513902198610090789` |
| `password` | 明文密码的 **MD5 大写** | `B63CDF08803D69F72715527B1ED1FF5A` |
| `device` | 固定 `2`（Web） | `2` |
| `hierarchy` | 站点层级码 | `A1-1-1-1-` |

密码哈希：`md5(utf8_password).hexdigest().upper()`

## 3. 成功响应

```json
{
  "success": true,
  "code": 0,
  "msg": "成功",
  "data": {
    "userId": "1695942673220665",
    "name": "缪继",
    "phone": "182******09",
    "idNumber": "513*************89",
    "token": "<32位hex>",
    "hierarchy": "A1-1-1-1-",
    "state": 1,
    "isAuth": 5
  }
}
```

## 4. 失败码（观测）

| code / 场景 | 含义 | 处理 |
|---|---|---|
| `code != 0` 或 `success: false` | 业务失败 | 读 `msg` |
| `401` + `token验证过期,请重新登录!` | token 失效 | 重新登录 |
| HTTP 5xx | 网关/服务异常 | 重试 |

登录错误文案因账号而异（如密码错误、用户不存在），以 `msg` 为准。

## 5. 登录后会话

本站**不使用**业务 Cookie，会话凭据为 **token**：

| 存储 | 键 | 说明 |
|---|---|---|
| `localStorage` | `user_token` | 登录返回的 `data.token` |
| 自动化持久化 | `data/cookies.json` | `{"user_token": "...", "user_id": "..."}` |
| 用户资料 | `data/user_profile.json` | 登录 `data` 全量 |

后续 API 请求在 **query params** 附带：

- `token=<user_token>`
- `device=2`
- `hierarchy=A1-1-1-1-`

POST 请求体经 `qs.stringify`，token 同样通过拦截器合并进 params。

## 6. 会话检查接口

| 项 | 值 |
|---|---|
| Method | `GET` |
| URL | `https://api.cdwork.cn/user/user/get_userByToken` |
| Params | `token`, `device`, `hierarchy` |

有效会话：`success: true` 且 `code: 0`。  
失效：`code: 401`，`msg: token验证过期,请重新登录!`

备用：`GET /user/user/query_user`（同样需 token 参数）。

## 7. 验证码流程

**无**。`imageCode` 接口存在但账号登录路径不调用。

## 8. 业务入口（Phase 2 参考）

登录后可访问「我的培训」：`https://www.wlxy.org.cn/pages/mine/mytrain/list`  
列表展示按年度的公需科目培训（如 2026/2025/2024…），B 型按 `target_years` 驱动学习。
