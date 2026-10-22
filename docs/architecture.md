# 结构与调度

`vendor/moonuestc/` 的十个模块保留上游认证、位置检查、提交声明、SQLite 状态和回读逻辑，校验值见 `UPSTREAM.json`。本项目只增加运行入口、账号存储、静态页面和路由器集成。

| 文件或目录 | 职责 |
| --- | --- |
| `lite.py` | 单账号执行；真实提交必须显式 `--submit`，`scheduled` 先检查暂停开关 |
| `multi.py` | 单进程顺序执行，账号间隔 20 秒，一个账号失败后继续 |
| `account_store.py` | 私有账号 CRUD、迁移、过滤公开索引、更新 cron |
| `account_api.py` | 按需 CGI，复用 rpcd 管理会话 |
| `profiles/` | 私有账号文件及索引，安装后作为配置来源 |
| `state/` | 既有 Cookie、SQLite 每日提交保护；按学号及认证资料隔离 |
| `scheduler/` | 配置编辑与任务共用的执行锁 |
| `web/index.html` | 唯一网页源文件，无框架或外链 |

`run.sh` 调用 `multi.py checkin --due --submit`。cron 为每个启用的时间保留一条任务，同分钟的账号合并执行。进程记录启动分钟，再等待调度锁；拿锁后读取配置，选择该分钟仍启用的账号，通过 `lite.py scheduled` 再次检查暂停开关。相邻批次最多等待 1800 秒，避免锁忙时直接漏跑。手动检查最多等待 5 秒。

配置编辑同时获取调度锁和状态锁。保存失败会撤回配置；cron 只替换本项目及旧版的标记条目。旧配置迁移为 `me`，保留原启用状态、执行时间、公开历史、Cookie 和提交保护。更换学号会清空该账号公开历史，更换认证资料会清除旧认证提示。删除账号保留私有状态中的提交保护，重新添加同一学号也不会绕过当日声明。

uhttpd 提供 `/moonuestc/index.html`、`accounts.json` 和 `status-<id>.json`。公开索引仅包含名称、脱敏学号、计划、启用状态和地点名，状态仅保留允许的字段。刷新只读本地缓存。

`/cgi-bin/moonuestc-api` 提供 `session`、`login`、`logout`、`get`、`save`、`delete`、`diagnose`；协议见 [API.md](API.md)。CGI 每次请求启动 Python 后退出。`diagnose` 启动一个后台单次只读任务，结束后退出，无签到提交接口。

认证通过本机 `http://127.0.0.1/ubus` 转接 rpcd，检查 `luci-base` 写权限。密码与可信指纹不回传；管理员才能取得用于编辑的完整学号。Cookie 使用 HttpOnly、SameSite=Strict；HTTPS 访问时增加 Secure。原版的应用用户管理与加密保险库没有移植。

安装器固定使用 `/www/moonuestc` 和 `/www/cgi-bin/moonuestc-api`，运行目录由安装器本身的位置决定。拒绝覆盖未带本项目标记的网页或 CGI；升级已有账号时不请求学校，不改变计划开关。

三端共用同一份 `web/index.html`，平台名称、API 入口和授权方式通过 `web/platform.js` 注入。安装时需一并部署这两个文件。新增账号默认暂停计划；参数及来源见 [parameters.md](parameters.md)。
