# MoonUESTC-OpenWrt

基于 [MoonUESTC](https://github.com/horoscope963852/MoonUESTC) 的 OpenWrt 低占用版本。Python 按任务启动，网页复用 uhttpd，管理操作使用按需 CGI，不增加常驻 Python 服务。

支持最多 20 个账号，分别配置地点、执行时间和启用状态。网页可切换账号、添加、编辑、删除，以及发起只读检查；管理操作使用路由器 root 管理密码解锁。

## 与上游的区别

| 部分 | 本版本 |
| --- | --- |
| 学校认证、范围及时段判断、提交和回读 | 十个上游模块原样保留 |
| Flask 后台、注册、用户权限、Docker | 不包含 |
| 调度 | OpenWrt cron；同一时间去重，多账号顺序执行，间隔 20 秒 |
| 状态页 | 单个静态 HTML + 脱敏 JSON；刷新不访问学校 |
| 管理认证 | 复用 rpcd 管理会话，Cookie 有效期 900 秒 |
| 私密数据 | 配置、Cookie、数据库位于私有目录，文件权限 0600；没有原版加密保险库 |

不绑定宿舍或路由器型号。已在 CR6608 / OpenWrt 24.10.8 验证登录、位置检查和多账号网页管理；首次真实签到尚未验证。

## 安装

需要已启用 LuCI 的 OpenWrt，uhttpd 提供 `/cgi-bin` 和 `/ubus`，rpcd 允许 root 登录及 `luci-base` 写权限。当前认证桥接使用本机 HTTP 80 端口。运行前确认系统时间及 cron 时区为北京时间。

将仓库文件放到路由器 `/root/MoonUESTC-OpenWrt`，在使用 opkg 的系统中执行：

```sh
opkg update
opkg install python3-light python3-urllib python3-openssl python3-sqlite3 python3-logging python3-uuid python3-codecs python3-cryptodome
cd /root/MoonUESTC-OpenWrt
sh install.sh
```

访问 `http://路由器地址/moonuestc/`，点击“管理”输入路由器 root 管理密码，再添加账号。管理密码通过当前连接提交，建议使用已配置的 HTTPS 访问；仅在可信内网开放管理页。

填写学校账号、密码、可信浏览器指纹，以及实际配置的 GCJ-02 位置。指纹来自本人已完成学校验证的浏览器：开发者工具 → Application → Cookies → `idas.uestc.edu.cn` → `MULTIFACTOR_BROWSER_FINGERPRINT` 的 Value。编辑时密码、指纹留空表示保留。未配置位置时默认填入欣苑组团（GCJ-02：纬度 `30.674521`，经度 `104.096295`），可在“位置”中修改；已有位置保留。

如需先从命令行查询学校地点，可填写 `config.example.json` 的副本 `config.json`，执行 `python3 lite.py locations`。旧版 `config.json` 会在首次安装时只读校验并迁移为 `me`，保留原时间和启用状态；已有 `profiles/` 的升级不会重新迁移或重新登录学校。安装备份配置、原 cron 和网页，并保留其他 cron 条目。

## 运行与停用

安装后配置以 `profiles/<id>.json` 为准，旧 `config.json` 仅作迁移来源。网页关闭账号计划即可暂停，修改时间会同步更新 cron。账号名称、脱敏学号、计划和结果可被内网访客查看，秘密不进入公开状态文件。

```sh
python3 multi.py diagnose --account me    # 登录及状态查询，不提交
python3 multi.py prepare --account me     # 位置和时段检查，不提交
python3 multi.py checkin --account me --submit  # 手动提交并回读
cat last-run.log                         # 最近一批定时任务日志
```

二次验证或验证码需要本人处理；配置坐标不是实时 GPS。每账号独立状态及最多八条摘要，共享 `state/` 按学号隔离 Cookie 和每日提交保护。成功以学校记录回读为准，结果不明确时不会盲目重发。删除账号不会删除这些提交保护记录。

## 验证与来源

开发机运行 `python -m pip install -r requirements.txt`，然后 `python -m unittest discover -s tests`。测试使用合成配置，不访问学校。可用 Chrome 和 Node.js 执行 `node tests/check_ui.cjs` 检查网页；非默认 Chrome 路径使用 `CHROME_PATH` 环境变量指定。

[结构与调度](docs/architecture.md) · [管理 API](docs/API.md) · [上游版本与校验](UPSTREAM.json) · [来源声明](NOTICE.md) · [许可证](LICENSE)
