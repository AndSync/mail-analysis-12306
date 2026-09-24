# 12306 邮件分析（mail-analysis-12306）

从邮箱读取 12306 购票/退票/改签通知邮件，生成 HTML 出行统计报告，并通过 SMTP 发送到指定邮箱。

- 纯 Python 标准库实现，无需安装任何依赖
- 自带 MCP 服务器（3 个工具），**邮箱未配置前强制拒绝运行分析**
- 核心工具是独立 CLI，任何 agent 都能直接调用
- 本仓库既是插件源码，也是可发布的插件市场（`.claude-plugin/marketplace.json`，ZCode 与 Claude Code 均识别）

## 仓库结构

```
├── .zcode-plugin/plugin.json   # ZCode 插件清单（userConfig 可视化配置）
├── .claude-plugin/
│   ├── plugin.json             # Claude Code 兼容清单
│   └── marketplace.json        # 市场清单（发布用，source 指向仓库根）
├── .mcp.json                   # ZCode MCP 服务器声明（user_config 模板注入）
├── src/
│   ├── main.py                 # CLI 入口
│   ├── mcp_server.py           # MCP 服务器（stdio JSON-RPC，仅标准库）
│   └── engine/                 # 核心逻辑（IMAP → 解析 → 分析 → 报告 → SMTP）
├── config/
│   ├── config.json             # 配置模板（占位值，勿提交真实授权码）
│   └── config_cities.json      # 城市/站点别名映射
├── skills/mail-analysis-12306/ # 插件 skill
├── assets/                     # 图标源文件 + 生成脚本
└── docs/TECHNICAL.md           # 技术文档
```

## 邮箱配置（首次使用必做）

1. 开启邮箱的 IMAP/SMTP 服务并生成**授权码**（不是登录密码）。QQ 邮箱：网页版 → 设置 → 账户 → 开启 POP3/IMAP/SMTP 服务 → 生成授权码。
2. 各 agent 的填写位置见下方对应章节。

| 邮箱 | IMAP 服务器 | SMTP 服务器 |
|------|-------------|-------------|
| QQ（已测试） | imap.qq.com | smtp.qq.com |
| 163 | imap.163.com | smtp.163.com |
| Gmail | imap.gmail.com | smtp.gmail.com |
| Outlook | outlook.office365.com | smtp.office365.com |

端口通常为 IMAP 993、SMTP 465（SSL）。可选：IMAP 文件夹（QQ 邮箱 12306 邮件常在「网上购票」）。

## 安装与配置

### ZCode（推荐，支持可视化配置界面）

1. **插件市场 → 添加 → 添加插件市场**，粘贴本仓库的 GitHub 地址（如 `https://github.com/<你的账号>/mail-analysis-12306`）。
2. 在 **个人 → 12306-mail-tools** 找到「12306邮件分析」，点击安装。
3. **设置 → 插件管理 → 12306邮件分析 → 详情 → 高级设置（Advanced）**，填写：
   - 邮箱地址（必填；读取 12306 邮件的账号，同时作为发件账号——扫描与发送报告共用同一邮箱）
   - IMAP/SMTP 授权码（必填；ZCode 暂无加密凭据存储，此值明文保存在本机配置中）
   - 报告收件人（必填，单个邮箱）
   - 12306 邮件所在文件夹（QQ 邮箱默认「网上购票」，留空扫描全邮箱）
   - 服务器地址/端口（默认 QQ 邮箱，通常不用改）
4. **重启会话**（或重启 ZCode），然后新建任务说：
   > 分析我的 12306 出行记录，把统计报告发到我的邮箱

本地开发调试：把仓库所在目录（如 `D:\WorkSpace\Agent\plugins`，需先在该目录生成 `marketplace.json`）添加为市场即可。

### Claude Code

```bash
/plugin marketplace add <你的GitHub账号>/mail-analysis-12306
/plugin install mail-analysis-12306@12306-mail-tools
```

Claude Code 没有 userConfig 表单，邮箱信息通过配置文件提供（MCP 服务器自动回退到配置文件）：编辑 `~/.zcode/mail-analysis-12306/config.json`，或设置环境变量 `MAIL12306_CONFIG` 指向你自己的配置文件：

```json
{
  "email": {
    "sender_email": "你的邮箱",
    "sender_password": "你的IMAP/SMTP授权码",
    "recipient_email": ["收件人@example.com"]
  },
  "imap_server": "imap.qq.com",
  "imap_port": 993,
  "smtp_server": "smtp.qq.com",
  "smtp_port": 465,
  "analysis": { "mailbox_name": "网上购票", "max_emails": 10000 }
}
```

### Codex

在 `~/.codex/config.toml` 注册 MCP 服务器（路径改为本仓库克隆位置）：

```toml
[mcp_servers.mail12306]
command = "python"
args = ["/path/to/mail-analysis-12306/src/mcp_server.py"]
env = { MAIL12306_SENDER_EMAIL = "你的邮箱", MAIL12306_SENDER_PASSWORD = "授权码", MAIL12306_RECIPIENT_EMAIL = "收件人@example.com" }
```

不填 env 时同样回退到 `~/.zcode/mail-analysis-12306/config.json`（或用 `MAIL12306_CONFIG` 指定其他路径）。

### Trae 及其他支持 MCP 的 agent

在 MCP 设置中添加 stdio 服务器，command 为 `python`，args 为 `src/mcp_server.py` 的绝对路径，env 里按需填 `MAIL12306_SENDER_EMAIL`、`MAIL12306_SENDER_PASSWORD`、`MAIL12306_RECIPIENT_EMAIL`（或使用配置文件回退）。

### 命令行直接运行（任何环境）

```bash
python src/main.py --config /path/to/config.json
```

## MCP 工具

| 工具 | 作用 |
|------|------|
| `get_mail_config_status` | 查看配置状态（不回显授权码） |
| `save_mail_config` | 把配置写入用户配置文件（聊天内配置的备用方式） |
| `analyze_12306_mail` | 后台启动完整分析并发报告；未配置时硬性拒绝。立即返回，用 `get_analysis_status` 轮询结果 |
| `get_analysis_status` | 查看后台分析任务的运行状态与日志末尾 |

## 高级配置

配置文件 `analysis` 段：`mailbox_name`（IMAP 文件夹）、`max_emails`（最大读取封数，默认 10000）、`start_year` / `end_year` / `start_month` / `end_month`（统计时间范围）。

## 隐私说明

- 邮件只读取本机邮箱（IMAP），报告只发送到你填写的收件人（SMTP）。
- ZCode 高级设置中的授权码、配置文件中的密码均为**本机明文存储**；请勿把真实授权码提交到代码仓库（`config.json` 请保持占位值，或取消 .gitignore 中 config.json 的注释后使用本地版本）。

## 故障排查

| 现象 | 处理 |
|------|------|
| 提示"邮箱尚未配置" | 填写配置（ZCode 改高级设置后需重启会话） |
| IMAP 连接失败 | 确认授权码正确、IMAP 服务已开启、服务器地址与端口匹配 |
| 邮件很少/没找到 | IMAP 文件夹填 `网上购票`，或留空扫描全邮箱 |
| 发送失败 | 确认 SMTP 服务已开启、授权码正确、SMTP 端口为 465 |

## 发布与版本管理

1. 推送到 GitHub 公开仓库，用户用仓库 URL 添加市场即可安装。
2. 国内用户可镜像到 Gitee，同样以 Git URL 方式添加。
3. 发布新版本：修改 `.zcode-plugin/plugin.json`、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` 与 `mcp_server.py` 中 `SERVER_INFO` 的版本号（保持四处一致），提交并打 tag。
4. 插件图标：源文件在 `assets/`（`icon.png` 512 / `icon-128.png` / `icon.svg`，由 `assets/gen_icon.py` 生成）。图标已以 data URI 内嵌在市场清单的 `icon` 字段（自包含，无需外部托管）。改图标后运行 `python assets/gen_icon.py` 重新生成，再同步 `icon` 字段。

## License

MIT
