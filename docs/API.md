# 管理 API

入口为 `/cgi-bin/moonuestc-api`。管理客户端必须从路由器私有 IP 打开的同源网页访问。POST 要求 `Content-Type: application/json` 和匹配的 Origin；请求体上限 16384 字节。接口不提供真实签到操作。

| action | 输入 | 权限及结果 |
| --- | --- | --- |
| `session` | 无；也可 GET `?action=session` | 返回 `authenticated`，不返回配置 |
| `login` | 路由器 root 管理 `password` | rpcd 认证，设置 900 秒 Cookie |
| `logout` | 无 | 销毁会话并清除 Cookie |
| `get` | 可选账号 `id` | 管理认证；返回编辑字段及秘密已保存标志 |
| `save` | `account` 对象 | 管理认证；新增或编辑，返回无秘密 DTO |
| `delete` | 账号 `id` | 管理认证；删除账号及公开状态 |
| `diagnose` | 账号 `id` | 管理认证；排队执行只读诊断，返回 `queued: true` |

`account` 接受 `id`（编辑时）、`label`、`student_id`、`password`、`browser_fingerprint`、`run_at`、`automation_enabled` 和 `location`。时间为 `HH:MM`；位置包含 `name`、GCJ-02 `latitude` 和 `longitude`。账号最多 20 个，禁止重复学号。编辑时密码或指纹为空字符串表示保留；读取接口只返回 `password_saved`、`fingerprint_saved`，不返回秘密内容。

请求示例，浏览器自动携带同源 Cookie 和 Origin：

```js
fetch('/cgi-bin/moonuestc-api', {
  method: 'POST',
  credentials: 'same-origin',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({action: 'get', id: 'me'})
}).then(r => r.json());
```

成功响应包含 `ok: true`；失败包含 `ok: false` 和不含秘密的 `message`。未认证返回 401，来源不匹配返回 403，任务占用或重复学号返回 409，非 JSON 返回 415，过大请求返回 413。只读诊断至少间隔 20 秒，频率超限返回 429，启动失败返回 503 并清除忙碌提示。

Cookie 名为 `moonuestc_admin`，Path 为 `/cgi-bin/moonuestc-api`，HttpOnly、SameSite=Strict；HTTPS 下增加 Secure。认证仅转接本机 rpcd，没有另存管理密码。公开状态文件不要求管理认证，不应将此页面或路由器管理服务开放到公网。

统一页面根据 `web/platform.js` 选择本平台接口与授权方式；新增账号草稿默认 `automation_enabled: false`。字段来源见 [parameters.md](parameters.md)。
