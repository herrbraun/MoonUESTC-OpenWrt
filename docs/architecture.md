# Windows 轻量版结构

| 组件 | 职责 |
| --- | --- |
| `vendor/moonuestc/` | 十个原样保留的认证、位置检查、提交保护及回读模块 |
| `lite.py` / `multi.py` | 单次执行、多账号隔离、暂停保护及顺序调度 |
| `windows_schedule.py` | 每安装目录一个原生 Windows 任务，合并启用时间 |
| `run_task.py` | 隐藏执行入口，任务结束退出，覆盖写入最近日志 |
| `desktop.py` | 按需开启的本机 HTTP 管理页，不作为服务安装 |
| `account_api.py` | 已认证请求的账号增删改与只读检查 |
| `secret_store.py` | 当前用户 DPAPI，密码与指纹磁盘加密 |
| `account_store.py` | 私有账号文件、脱敏公开数据、计划更新与回滚 |
| `tools/install_windows.py` | 初始化仅用户、SYSTEM、管理员可访问的私有目录 |

任务 XML 为每个启用时间生成一个 CalendarTrigger，使用 `+08:00`，同一时刻去重。任务采用 InteractiveToken、LeastPrivilege，运行 `pythonw.exe run_task.py`，不保存 Windows 登录密码。系统设置 Parallel，先按触发时刻启动批次，再由应用调度锁串行处理，以保留各批启动分钟；不自动重试或补跑错过的任务。

`run_task.py` 调用 `multi.py checkin --due --submit`。进程先记录启动分钟，拿调度锁后读取仍启用的账号，再调用 `scheduled` 暂停保护。账号间隔 20 秒，单账号失败继续后续账号。共享 SQLite 和 Cookie 按学号及认证资料隔离，上游每日提交保护及不明确结果回读保留。

保存或删除账号时更新本安装目录的系统任务；保存任务失败会撤回账号修改。任务名称和所有权标记来自程序目录摘要，更新和删除前核对所有权。计划文件通过临时 XML 和环境变量交给固定 PowerShell 脚本，路径不拼接为 PowerShell 代码。

本机页面只允许 `127.0.0.1` 访问。每次启动产生新随机密钥，使用 URL fragment 交给浏览器后从地址栏移除；请求在自定义头中携带密钥。服务同时验证 Host、Origin、JSON 和长度。文件访问白名单仅含网页及脱敏状态，不提供配置目录下载。

`POST /api` 仅接受 `get`、`save`、`delete`、`diagnose`，详见 [API.md](API.md)。诊断启动独立的短期只读进程，完成后退出；没有网页签到提交接口。页面和系统任务彼此独立。

密码和浏览器指纹通过 Windows 当前用户 DPAPI 加密；Cookie、SQLite 和日志由 NTFS 私有目录保护。没有沿用上游完整后台的用户管理、队列服务或加密保险库。
