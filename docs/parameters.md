# 参数与获取方法

三端表单一致。新增账号默认暂停计划，建议填完后先做只读检查，再启用定时执行。

## 必填内容

| 页面字段 / 配置键 | 填什么 | 从哪里获取 |
| --- | --- | --- |
| 名称 / `label` | 自己便于识别的名称 | 自定义，与学校认证无关 |
| 学号 / `student_id` | 学校统一认证使用的学号，作为字符串填写 | 本人的学校账号；程序接受 8–20 位数字 |
| 学校密码 / `password` | 统一身份认证密码 | 本人登录学校门户使用的密码，不是路由器或电脑密码 |
| 浏览器指纹 / `browser_fingerprint` | 32 位十六进制值 | 本人已完成二次验证的电脑浏览器，获取步骤见下文 |
| 执行时间 / `run_at` | 北京时间 `HH:MM` | 自选，需位于学校允许时段内；默认 `21:01` |
| 定时执行 / `automation_enabled` | 开启或暂停计划 | 初次默认关闭；确认配置后手动开启 |
| 位置名称 / `location.name` | 与坐标对应的地点名称 | 优先使用学校地点接口返回的 `locationName` |
| 纬度、经度 / `location.latitude`、`location.longitude` | GCJ-02 坐标，纬度在前、经度在后 | 优先查询学校返回的允许地点，见下文 |

默认位置为欣苑组团，纬度 `30.674521`、经度 `104.096295`。已有账号保留原位置；这些是配置值，不是设备实时 GPS。其他宿舍请改成学校给该账号返回的位置。

`location.mode=fixed`、`location.coordinate_system=gcj02` 由表单自动设置。配置文件中的 `location_radius_meter` 可选，只用于显示；真正允许范围始终由学校返回的围栏决定，修改它不能扩大签到范围。接口地址、CAS 参数、Ticket、会话 Cookie 由程序处理，无需手工填写。

## 获取可信浏览器指纹

1. 使用自己的 Chrome 或 Edge 打开[学校学工网页](https://jzsz.uestc.edu.cn/)，正常登录；学校要求验证码或二次验证时由本人完成。如页面提供“信任此浏览器”，按学校流程确认。
2. 在统一认证域名 `idas.uestc.edu.cn` 的页面按 `F12` 打开开发者工具。选择 **Application（应用）→ Storage（存储）→ Cookies → `https://idas.uestc.edu.cn`**。
3. 查找名称 **`MULTIFACTOR_BROWSER_FINGERPRINT`**，仅复制它的 **Value**。应是 32 位十六进制字符，不要复制 Cookie 名称、等号或整段 Cookie。
4. 如果登录后跳转导致 Application 中没有该域名：在开发者工具 **Network（网络）** 勾选 **Preserve log（保留日志）**，正常访问统一认证页面并完成登录；过滤 `idas.uestc.edu.cn`，在请求的 Cookie 或响应的 Set-Cookie 中查找同名值。
5. 粘贴到“浏览器指纹”，保存并点击“检查”。学校撤销信任后需要本人重新验证并更新此值，程序不自动绕过验证码或二次认证。

编辑账号时，学校密码和浏览器指纹留空表示保留已保存值。

## 查询学校允许的地点

先在页面录入账号、密码和指纹，保持计划关闭。账号 ID 是 `profiles/` 中对应 JSON 的文件名（不含 `.json`，排除 `index.json`）；迁移的旧账号 ID 为 `me`。进入源码目录，将下列命令的 `账号ID` 替换为实际值：

```powershell
# Windows PowerShell
& .\.venv\Scripts\python.exe lite.py locations --config .\profiles\账号ID.json
```

```sh
# Linux
./.venv/bin/python lite.py locations --config profiles/账号ID.json

# OpenWrt
python3 lite.py locations --config profiles/账号ID.json
```

`locations` 只登录和查询，不提交。输出中的 `locationName`、`latitude`、`longitude`、`radiusMeter` 来自学校，按对应值填写位置。不要将 WGS-84 或其他坐标直接当作 GCJ-02 使用。

位置填完后，可用同一命令将 `locations` 换成 `prepare`，检查配置坐标、学校范围和时段；不提交。页面“检查”对应 `diagnose`，查询认证和考勤状态，不等同于完整位置校验，更不等同于真实签到成功。

## 各平台还需要什么

| 平台 | 平台管理凭据与运行条件 |
| --- | --- |
| OpenWrt | 页面管理使用路由器 root 管理密码；需要现有 LuCI/uhttpd/rpcd，cron 系统时区必须为北京时间 |
| Windows | 不需要 Windows 登录密码；启动脚本自动交付本次本机管理密钥。任务以当前用户运行，电脑开机且用户保持登录，锁屏可运行 |
| Linux | 不需要额外网页密码；启动脚本自动交付本次本机管理密钥。启用计划需 `systemctl --user` 可用；退出登录后继续运行需配置用户 linger |

三端只允许管理自己或已获明确授权的账号。学校最终决定认证、位置、时段与考勤结果；只读检查通过不代表真实签到已经完成。
