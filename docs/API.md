# 本机管理 API

`POST /api` 仅在本次管理进程绑定的 `http://127.0.0.1:<随机端口>` 上可用。请求必须具有匹配的 Host、Origin、`Content-Type: application/json` 及 `X-MoonUESTC-Key` 启动密钥；请求体上限 16384 字节。密钥只在本次进程生命周期内有效，不需要路由器密码或 Linux 登录密码。

| action | 输入 | 返回 |
| --- | --- | --- |
| `get` | 可选账号 `id` | 编辑 DTO，以及秘密已保存标记 |
| `save` | `account` | 保存后的无秘密 DTO；同步 Windows 任务 |
| `delete` | 账号 `id` | 删除账号及公开状态；保留每日提交保护 |
| `diagnose` | 账号 `id` | `queued: true`，后台执行只读检查 |

没有登录、注册、远程管理或签到提交接口。随机启动密钥由启动脚本打开的浏览器自动接收，页面使用后从地址栏移除。

`account` 接受 `id`（编辑时）、`label`、`student_id`、`password`、`browser_fingerprint`、`run_at`、`automation_enabled` 和 `location`。最多 20 个账号，禁止重复学号；时间为 `HH:MM`，位置为 GCJ-02。编辑时密码、指纹为空字符串代表保留。读取只返回 `password_saved`、`fingerprint_saved`，不返回秘密。

成功返回 `ok: true`；失败返回 `ok: false` 及脱敏的 `message`。缺少启动密钥返回 401，Host 或 Origin 不匹配返回 403，锁占用或重复学号返回 409，非 JSON 返回 415，过大请求返回 413。诊断至少间隔 20 秒，超限返回 429；启动失败返回 503 并清除忙碌状态。

静态 GET 白名单为 `/`、`/platform.js`、`/accounts.json`、`/status-<id>.json`；配置、源文件和其他路径均不可下载。页面刷新只读取这些本地文件，不访问学校。

统一页面根据 `web/platform.js` 选择本平台接口与授权方式；新增账号草稿默认 `automation_enabled: false`。字段来源见 [parameters.md](parameters.md)。
