# MoonUESTC-OpenWrt

基于 [MoonUESTC](https://github.com/horoscope963852/MoonUESTC) 的 OpenWrt 低占用版本。Python 按任务启动，网页复用 uhttpd，不新增常驻网页进程。

## 改了什么

| 部分 | 本版本 |
| --- | --- |
| 学校认证、签到、范围与时段判断、提交回读 | 保留上游实现 |
| 完整网页后台、用户管理、注册、队列、Docker | 不包含 |
| 调度 | OpenWrt cron，每日单次执行 |
| 网页 | 静态 HTML + 过滤后的状态 JSON，刷新不请求学校 |
| 配置与 Cookie | 路由器私有目录，文件权限 0600 |
| 依赖 | Python 标准库模块、PyCryptodome；无 Flask、Waitress、Argon2、ALTCHA |

不绑定宿舍或路由器型号。已验证 CR6608 / OpenWrt 24.10.8；其他设备未实机验证。登录、位置检查及页面已通过，首次真实签到尚未验证。

## 安装

在使用 opkg 的 OpenWrt 上，以 root 执行：

```sh
opkg update
opkg install python3-light python3-urllib python3-openssl python3-sqlite3 python3-logging python3-uuid python3-codecs python3-cryptodome
cd /root/MoonUESTC-OpenWrt
cp config.example.json config.json
chmod 600 config.json
vi config.json
```

填写学号、密码、可信浏览器指纹和位置。指纹来自本人已完成学校验证的浏览器：开发者工具 → Application → Cookies → `idas.uestc.edu.cn` → `MULTIFACTOR_BROWSER_FINGERPRINT` 的 Value。

查询学校允许的地点，再填写对应 GCJ-02 经纬度、地点名称和半径：

```sh
python3 lite.py locations
python3 lite.py prepare
sh install.sh
```

安装器先做只读检查，通过后设置 cron 并启用网页。默认北京时间 21:01；运行前确认路由器时区为 `Asia/Shanghai`。安装保留其他 cron 条目，并备份配置和原 crontab。

访问 `http://路由器地址/moonuestc/`。网页只展示结果，不提供账号配置或提交按钮。

## 运行与停用

```sh
python3 lite.py diagnose                  # 登录及状态查询
python3 lite.py prepare                   # 位置和时段检查，不提交
python3 lite.py checkin --submit          # 在学校时段内提交并回读
cat last-run.log                         # 最近一次定时任务日志
```

将 `config.json` 的 `automation_enabled` 改为 `false` 可暂停自动执行。修改 `run_at` 后重新运行 `sh install.sh`。二次验证或验证码需要本人处理；配置坐标不是实时 GPS。

状态、Cookie 和提交记录在 `state/`；网页最多保留八条任务摘要。成功以学校记录回读为准，提交结果不明确时不会盲目重发。

## 来源与验证

保留的十个上游模块未修改，版本与校验值见 [UPSTREAM.json](UPSTREAM.json)。第三方声明见 [NOTICE.md](NOTICE.md)，许可证见 [LICENSE](LICENSE)。

开发机离线测试：`python -m pip install -r requirements.txt`，然后 `python -m unittest discover -s tests`。测试不使用真实账号或学校网络。
