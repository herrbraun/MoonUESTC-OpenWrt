# MoonUESTC · OpenWrt 轻量版

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

## 安装 OpenWrt 版

以下适用于已带 LuCI 的 OpenWrt 24.10 / opkg。需要 uhttpd 的 `/cgi-bin`、本机 `/ubus`、rpcd root 登录及 `luci-base` 写权限；已验证 CR6608 / OpenWrt 24.10.8，其他型号未实机验证。

下载 main 分支源码，上传到 `/root/MoonUESTC-OpenWrt`，以 root 执行：

```sh
opkg update
opkg install python3-light python3-urllib python3-openssl python3-sqlite3 python3-logging python3-uuid python3-codecs python3-cryptodome
cd /root/MoonUESTC-OpenWrt
sh install.sh
```

访问 `http://路由器地址/moonuestc/`，点击“管理”输入路由器 root 管理密码，再添加账号。仅在可信内网使用管理页，优先沿用路由器已有的 HTTPS 配置。首次空配置安装不访问学校。

安装保留其他 cron 条目及已有账号，并备份配置、原 cron 和网页。旧 `config.json` 在首次迁移前做只读校验，已有 `profiles/` 的升级不重新迁移或登录学校。运行前确认路由器系统和 cron 时区为北京时间，设备需在计划时间正常联网。

配置与 Cookie 使用私有目录、文件权限 0600，没有原版完整后台的加密保险库。最近定时日志为 `last-run.log`。

开发验证：`python -m unittest discover -s tests`、`node tests/check_ui.cjs`。

## 使用与数据

编辑账号时密码、指纹留空表示保留。页面“检查”只做认证和考勤查询；位置校验用 `prepare`，具体命令见参数文档。确认配置后再开启定时计划；关闭计划可暂停。最多 20 个账号，按需顺序执行，账号间隔 20 秒。

网页刷新只读本地缓存。提交成功以学校记录回读为准，结果不明确时不盲目重发；删除账号不会清除每日提交保护。二次验证由本人处理，配置坐标不是实时 GPS。

`profiles/`、`state/`、`runtime/` 和日志均不进入 Git。不同平台请使用独立源码目录并重新录入凭据，不要将真实运行数据上传仓库。

## 验证与来源

测试使用合成账号，不登录学校、不触发真实签到。三端包含离线测试与桌面/手机页面检查，Linux 另有原生 systemd 单元校验。首次真实签到仍待验证。

原作者与第三方来源见 [NOTICE.md](NOTICE.md)，完整许可保留于 [LICENSE](LICENSE) 和 `licenses/`。上游参考的 GoodNight、UESTC-MoonCheck、coordtransform 及相应作者声明均保留。

[参数获取](docs/parameters.md) · [结构与调度](docs/architecture.md) · [管理 API](docs/API.md)
