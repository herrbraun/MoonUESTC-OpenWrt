# MoonUESTC · Windows 轻量版

同一仓库的两个分支：[main：OpenWrt](https://github.com/herrbraun/MoonUESTC-OpenWrt/tree/main) · [windows：Windows](https://github.com/herrbraun/MoonUESTC-OpenWrt/tree/windows)。两版复用相同的 MoonUESTC 认证、签到和回读核心。

Windows 版只依赖 **Python 标准库 + PyCryptodome**。系统任务按时启动 Python，执行后退出；管理页需要时才打开，关闭窗口即结束。没有 Flask、Docker、数据库服务、前端构建链或常驻托盘程序。

## 使用

1. 安装 Python 3.10 或更新版本，下载本分支到当前 Windows 用户自己的文件夹。
2. 双击 **安装.cmd**，创建本地虚拟环境、安装唯一的第三方依赖并初始化私有目录。安装不访问学校。
3. 双击 **启动管理页.cmd**。浏览器自动打开本机页面，添加学校账号、可信浏览器指纹和位置。
4. 保存启用的计划后，Windows 任务计划程序接管定时运行。可以关闭管理窗口。

默认每日北京时间 **21:01**，默认地点为欣苑组团，GCJ-02 纬度 `30.674521`、经度 `104.096295`，均可修改。最多 20 个账号，各自拥有计划和状态；相同时间合并触发，账号间隔 20 秒。

可信浏览器指纹来自本人已完成验证的浏览器：开发者工具 → Application → Cookies → `idas.uestc.edu.cn` → `MULTIFACTOR_BROWSER_FINGERPRINT` 的 Value。编辑账号时密码、指纹留空表示保留。二次验证或验证码仍需本人处理。

管理页的“检查”只做登录和状态查询，不提交签到；页面刷新只读取本地缓存。成功以学校记录回读为准，提交结果不明确时不会盲目重发。配置坐标不是实时 GPS。

## 定时运行

Windows 系统任务以当前用户权限运行，时间使用明确的 `+08:00` 偏移，不依赖电脑当前时区。电脑需要开机，且该用户仍处于登录状态；锁屏可以运行，注销或关机不能运行。睡眠唤醒取决于系统电源策略，错过的任务不会补交。

在网页关闭账号计划可停用该账号，全部关闭会移除本安装目录的任务。**移除定时任务.cmd** 只删除本安装目录对应的任务，保留账号和历史；以后保存启用的计划可重新安装任务。移动程序目录前先移除旧任务，再从新目录运行安装。

任务名称为 `MoonUESTC-Windows-<目录摘要>`，不会覆盖其他程序的任务。签到执行时隐藏窗口，日志写入 `runtime/last-run.log`，不需要管理页保持打开。

## 数据与本机访问

- 管理页仅绑定 `127.0.0.1`，使用本次启动的随机密钥，浏览器自动接收；不需要路由器密码或 Windows 密码。普通复制地址不会携带管理权限，重新打开时使用启动脚本。
- `profiles/` 内的学校密码和指纹通过当前 Windows 用户的 DPAPI 加密；编辑接口不回传秘密。更换 Windows 用户或电脑后需要重新填写这些资料。
- Cookie 和 SQLite 提交保护保存在 `state/`，使用 NTFS 私有目录权限保护。公开状态只包含脱敏学号和允许的结果字段。
- `runtime/`、`profiles/`、`state/`、日志不进入 Git。不要复制 OpenWrt 的真实运行目录到仓库。

旧 `config.json` 可迁移为 `me`，但原始文件仍可能含明文秘密；推荐直接使用本机网页录入。删除账号保留每日提交保护，重新添加同一学号不会绕过当日声明。

## 开发与验证

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests
node tests/check_ui.cjs
```

已通过本机 24 项测试、Windows 原生任务注册、NTFS 私有权限与浏览器检查；首次真实签到尚未验证。

Python 测试仅在 Windows 上运行，使用合成账号；HTTP 测试只连接本机。网页测试需要 Chrome 和 Node.js，非默认 Chrome 路径用 `CHROME_PATH` 指定。测试不登录学校、不提交真实签到。

[结构与调度](docs/architecture.md) · [本机 API](docs/API.md) · [上游版本](UPSTREAM.json) · [来源声明](NOTICE.md) · [许可证](LICENSE)
