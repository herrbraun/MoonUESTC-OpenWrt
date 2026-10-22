# 项目约定

- 只维护 OpenWrt 版本；不引入常驻 Python 网页服务或前端构建链。
- `vendor/moonuestc/` 保持上游原样；更新时同步 `UPSTREAM.json` 和许可证。
- 学校请求保留 HTTPS 校验，限制目标为学校认证与学工域名。
- 公开静态数据仅含脱敏学号和状态；管理读写必须验证 rpcd 会话，不回传密码、指纹或 Cookie。
- CGI 只允许只读学校检查，不增加签到提交接口；保持同源校验和 JSON 请求限制。
- 多账号调度走 `multi.py`；`--due` 保留启动分钟并调用 `scheduled` 暂停保护。
- 配置修改与任务共用调度锁；迁移保留账号、Cookie、提交保护、时间和启用状态。
- 只读检查与真实提交保持区分；成功必须有学校记录回读。
- 真实账号、运行数据和设备访问资料不得进入 Git。
- 安装器保留其他 cron 条目，不覆盖无关网页。
- 安装路径由程序位置确定；网页与 CGI 分别使用 `/moonuestc/`、`/cgi-bin/moonuestc-api`。
- 测试使用合成配置，不访问学校；命令见 README。
- 三分支 `web/index.html` 与 `tests/check_ui.cjs` 保持完全一致；平台差异只放 `web/platform.js`。
