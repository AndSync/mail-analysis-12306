---
name: mail-analysis-12306
description: 分析邮箱中的 12306 火车票购票/退票/改签邮件，生成 HTML 出行统计报告并发送到指定邮箱。用户要求统计 12306 出行、生成火车票分析报告、或把报告发到邮箱时使用。
---

# 12306 邮件分析

从邮箱读取 12306 购票/退票/改签通知邮件，生成 HTML 出行统计报告，并通过 SMTP 发送到指定邮箱。

核心是随仓库分发的独立 Python 工具（仅标准库、零第三方依赖）：`src/main.py` + `src/engine/`。它可以通过三种方式使用：

1. **命令行**（任何环境）：`python src/main.py --config <配置文件路径>`
2. **MCP 服务器**（支持 MCP 的 agent，如 ZCode/Claude Code/Codex/Trae）：`python src/mcp_server.py`
3. **可视化配置**（ZCode 专属）：插件详情 → 高级设置表单，值经 MCP 注入

## 工作流程

1. **确认配置**：邮箱信息（邮箱地址、IMAP/SMTP 授权码、报告收件人）是否已配置。
2. **运行分析**：读取 12306 邮件 → 解析票务记录 → 统计分析 → 生成 HTML 报告 → 发送到收件邮箱。
3. **结果反馈**：报告已发送到收件邮箱，附关键统计（出行次数、消费总额、退改扣费等）。

## 邮箱配置

需要三类信息：

- **邮箱地址**：读取 12306 邮件的账号，同时也是发件账号（扫描与发送报告共用同一邮箱）
- **IMAP/SMTP 授权码**：不是登录密码（QQ 邮箱：设置 → 账户 → 开启 IMAP/SMTP 服务 → 生成授权码）
- **报告收件人**：单个邮箱地址

默认 QQ 邮箱服务器（imap.qq.com:993 / smtp.qq.com:465，已实测）。其他邮箱改服务器地址即可：

| 邮箱 | IMAP 服务器 | SMTP 服务器 |
|------|-------------|-------------|
| QQ（已测试） | imap.qq.com | smtp.qq.com |
| 163 | imap.163.com | smtp.163.com |
| Gmail | imap.gmail.com | smtp.gmail.com |
| Outlook | outlook.office365.com | smtp.office365.com |

### 配置方式（按使用场景）

- **命令行**：写配置文件（见 `config/config.json` 模板），`python src/main.py --config /path/to/config.json`。也可用 `MAIL12306_CONFIG` 环境变量指向配置文件。
- **MCP 服务器**：`save_mail_config` 工具写入用户目录配置文件；或用环境变量 `MAIL12306_SENDER_EMAIL` / `MAIL12306_SENDER_PASSWORD` / `MAIL12306_RECIPIENT_EMAIL`。
- **ZCode 可视化**：插件详情 → 高级设置填写，重启会话生效。

## MCP 工具（`src/mcp_server.py`）

| 工具 | 作用 |
|------|------|
| `get_mail_config_status` | 查看配置状态（是否已配置、来源、缺哪些字段；不回显授权码） |
| `save_mail_config` | 把配置写入用户配置文件（聊天内配置的备用方式） |
| `analyze_12306_mail` | 后台启动完整分析并发报告；未配置时硬性拒绝。立即返回，不等待完成 |
| `get_analysis_status` | 查看后台分析任务的状态与日志末尾，轮询直到完成 |

## 统计口径（重要）

- **出行次数** = 退改抵消后的真实乘坐记录（退票的、改签前作废的旧票、改签后再退的都不算）
- **消费总额** = 实际净支出 = 购票实付 + 改签补差 − 改签退差 − 退票退款
- **退改扣费** = 退票手续费 + 改签手续费（退票/改签因时间原因被扣的费用）
- 城市统计排除同城行程（出发城市 == 到达城市）；车站名经 `config/config_cities.json` 别名映射归并到主城市

## 可选配置

配置文件 `analysis` 段：`mailbox_name`（IMAP 文件夹，QQ 邮箱常用「网上购票」）、`max_emails`（最大读取封数，默认 10000）、`start_year` / `end_year` / `start_month` / `end_month`（统计时间范围）。

## 故障排查

| 现象 | 处理 |
|------|------|
| 提示"邮箱尚未配置" | 填写配置（ZCode 改高级设置后需重启会话） |
| IMAP 连接失败 | 确认授权码正确、IMAP 已开启、服务器地址与端口匹配 |
| 邮件很少/没找到 | 设置 `analysis.mailbox_name` 为 `网上购票`，或留空扫描全邮箱 |
| 发送失败 | 确认 SMTP 已开启、授权码正确、SMTP 端口 465 |

## 参考

- 技术细节见 [TECHNICAL.md](../../docs/TECHNICAL.md)
- 安装与发布见 [README.md](../../README.md)
