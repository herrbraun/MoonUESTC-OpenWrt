# MoonUESTC · Linux 轻量版

基于原作者 **[horoscope963852](https://github.com/horoscope963852)** 的 **[MoonUESTC](https://github.com/horoscope963852/MoonUESTC)** 进行轻量化适配。学校认证、位置与时段判断、提交保护及结果回读的十个核心模块保持上游原样，版本及校验值见 [UPSTREAM.json](UPSTREAM.json)。

特色是 **按需运行、减少依赖、界面简洁**。仅依赖 Python 标准库与 PyCryptodome，不引入 Flask、Docker、前端构建链或额外常驻应用服务。三端使用完全相同的页面源码，保留多账号、独立计划、只读检查和状态记录。

| 分支 | 平台 | 调度与管理页 |
| --- | --- | --- |
| [main](https://github.com/herrbraun/MoonUESTC-OpenWrt/tree/main) | OpenWrt | cron，复用 uhttpd，按需 CGI |
| [windows](https://github.com/herrbraun/MoonUESTC-OpenWrt/tree/windows) | Windows | 系统任务计划，本机管理页按需启动 |
| [linux](https://github.com/herrbraun/MoonUESTC-OpenWrt/tree/linux) | Linux / systemd | 用户定时器，本机管理页按需启动 |

## 先准备参数

需要：**学号、学校密码、本人可信浏览器指纹、地点坐标、执行时间**。首次新增默认暂停计划；时间默认北京时间 `21:01`，位置默认欣苑组团（GCJ-02 纬度 `30.674521`、经度 `104.096295`），均可修改。

**[参数说明与获取方法](docs/parameters.md)** 包含每个字段、指纹的浏览器获取步骤、查询学校允许地点的命令，以及各平台的运行条件。建议先读这一页。

## 安装 Linux 版

需要 **采用 systemd 的 Linux、Python 3.10+、venv、tzdata**。启用计划时需有可用的 `systemctl --user`。请以日常使用的用户安装，不要用 sudo 运行安装脚本。

Debian / Ubuntu 可先准备依赖，再进入下载的 linux 分支源码目录：

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip tzdata
sh install.sh
sh start.sh
```

安装创建虚拟环境，唯一第三方 Python 依赖是 PyCryptodome。管理页按需启动，浏览器自动打开本机页面；配置后关闭页面和管理进程，不影响系统定时器。

每个启用时间使用独立的 systemd 用户 timer/oneshot 服务，明确按 `Asia/Shanghai` 触发；执行完退出，错过的任务不补交。机器需开机、正常联网。**如需退出 SSH 或桌面登录后继续运行，由管理员为该用户启用 linger**：

```sh
sudo loginctl enable-linger "$USER"
```

这只保持用户 systemd 管理器可用，不会将网页设为常驻服务。可用 `systemctl --user list-timers 'moonuestc-*'` 查看计划。关闭所有账号计划或执行 `sh remove-timers.sh` 移除本安装目录的定时器，不删除账号数据、不停止正在执行的签到服务。

### 无桌面的服务器

本机建立隧道：`ssh -L 8765:127.0.0.1:8765 用户@服务器`，然后在该 SSH 会话中进入源码目录：

```sh
sh start.sh --no-browser --print-url --port 8765
```

在自己的电脑浏览器打开输出链接。链接包含本次管理密钥，仅本人使用；按 Ctrl+C 结束管理页。服务始终只绑定回环地址，不对公网开放。

私有目录权限 0700、文件 0600，学校密码和指纹按文件权限保护，**没有额外加密**。最近日志为 `runtime/last-run.log`。

开发验证：`python -m unittest discover -s tests`、`python tools/check_systemd.py`、`node tests/check_ui.cjs`。浏览器测试需 Node.js 与 Chrome，非默认路径用 `CHROME_PATH` 指定；这些不是运行依赖。

## 使用与数据

编辑账号时密码、指纹留空表示保留。页面“检查”只做认证和考勤查询；位置校验用 `prepare`，具体命令见参数文档。确认配置后再开启定时计划；关闭计划可暂停。最多 20 个账号，按需顺序执行，账号间隔 20 秒。

网页刷新只读本地缓存。提交成功以学校记录回读为准，结果不明确时不盲目重发；删除账号不会清除每日提交保护。二次验证由本人处理，配置坐标不是实时 GPS。

`profiles/`、`state/`、`runtime/` 和日志均不进入 Git。不同平台请使用独立源码目录并重新录入凭据，不要将真实运行数据上传仓库。

## 验证与来源

测试使用合成账号，不登录学校、不触发真实签到。三端包含离线测试与桌面/手机页面检查，Linux 另有原生 systemd 单元校验。首次真实签到仍待验证。

原作者与第三方来源见 [NOTICE.md](NOTICE.md)，完整许可保留于 [LICENSE](LICENSE) 和 `licenses/`。上游参考的 GoodNight、UESTC-MoonCheck、coordtransform 及相应作者声明均保留。

[参数获取](docs/parameters.md) · [结构与调度](docs/architecture.md) · [管理 API](docs/API.md)
