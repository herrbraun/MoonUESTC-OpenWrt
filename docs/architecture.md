# Linux 轻量版结构

Linux 分支支持 systemd 用户定时器，三端共享同一份 `web/index.html`。平台名称、API 与授权方式仅由 `web/platform.js` 决定。

| 组件 | 职责 |
| --- | --- |
| `vendor/moonuestc/` | 十个未改动的认证、范围、提交声明与回读模块 |
| `lite.py` / `multi.py` | 单次执行、多账号隔离、暂停保护、批次调度锁 |
| `linux_schedule.py` | 用户 timer/oneshot 单元生成、安装、所有权检查及失败恢复 |
| `run_task.py` | 单批次执行入口、独立临时日志及最终日志原子替换 |
| `desktop.py` / `account_api.py` | 按需本机管理页、只读诊断和账号管理 |
| `account_store.py` / `secret_store.py` | 私有 JSON 配置、迁移与脱敏状态；不额外加密 |
| `tools/install_platform.py` | 初始化权限 0700 的私有目录 |

每个安装目录使用独立摘要前缀，每个启用时间生成独立 `.timer` 和 `.service`，相同时间去重。`OnCalendar` 明确指定 `Asia/Shanghai`，精度 1 秒，`Persistent=false`，不自动重试或补交。

不同时间的服务独立启动，先记录启动分钟，再等待应用调度锁串行执行。这样前一批耗时较长时，不会吞掉后一时刻的触发。账号间隔 20 秒，单账号失败继续后续账号；`scheduled` 再次检查暂停开关。

保存账号时只更新带本安装目录所有权标记的单元，保留无关任务；失败恢复旧单元定义及原启用/活跃状态，并撤回账号修改。移除定时器不停止正在处理提交的 oneshot 服务，仍保留 SQLite 每日提交保护。

定时器依赖该用户的 systemd 管理器。退出登录后仍要运行时，由系统管理员按需配置用户 linger；程序不自动修改这个系统策略，也不安装常驻网页服务。

管理页仅绑定 `127.0.0.1`。浏览器以 URL fragment 接收本次随机密钥，随后从地址栏清除并放入标签页 sessionStorage。请求验证 Host、Origin、密钥、JSON 及大小；静态下载仅允许页面、平台配置和脱敏结果。无桌面时用 SSH 隧道及 `--print-url` 获取本次私有入口。

`POST /api` 支持 `get`、`save`、`delete`、`diagnose`，没有签到提交接口。`diagnose` 运行独立的短期只读进程，完成后退出。接口见 [API.md](API.md)，配置字段来源见 [parameters.md](parameters.md)。

私有目录为 0700，文件为 0600；密码、指纹、Cookie 和 SQLite 按访问权限保护，没有额外加密。不同平台使用独立目录，不复用 Windows DPAPI 密文。
