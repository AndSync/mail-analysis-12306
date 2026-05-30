---
name: mail-analysis-12306
description: Analyze 12306 rail ticket emails via IMAP/SMTP, generate HTML travel statistics, and send the report by email. Tested with QQ Mail; other IMAP providers should work with correct server settings. Requires config.json setup before first run. Use when the user asks for 12306 trip stats, rail ticket analysis, or a travel report from mailbox.
version: 1.0.0
metadata: {"openclaw":{"requires":{"bins":["python3"]},"emoji":"🚄"}}
---

# 12306 邮件分析

从邮箱读取 12306 购票/退票/改签通知，生成 HTML 出行统计报告并发送到指定邮箱。

独立 Python 工具，可直接运行；也可作为 OpenClaw skill 调用。

## 首次配置

编辑与 `main.py` 同目录下的 `config.json`，填写：

- `email.sender_email` — 邮箱地址
- `email.sender_password` — **IMAP/SMTP 授权码或应用专用密码**（多数邮箱不是登录密码）
- `email.recipient_email` — 报告收件人列表
- `imap_server` / `imap_port` — 收件服务器（读取 12306 邮件）
- `smtp_server` / `smtp_port` — 发件服务器（发送报告）

默认配置为 QQ 邮箱服务器地址，**目前仅在 QQ 邮箱上实测通过**。理论上任何支持 IMAP/SMTP 的邮箱，只要填对服务器和凭据即可使用，但其他邮箱尚未逐一测试，遇到问题需自行对照邮箱服务商文档调整。

不确定配置文件在哪？先运行一次程序，未配置时会**打印 config.json 的完整绝对路径**。

### 邮箱配置示例

**QQ 邮箱（已测试）**

1. 登录 QQ 邮箱网页版 → 设置 → 账户
2. 开启 POP3/IMAP/SMTP 服务
3. 生成授权码，填入 `sender_password`

```json
{
  "imap_server": "imap.qq.com",
  "imap_port": 993,
  "smtp_server": "smtp.qq.com",
  "smtp_port": 465
}
```

**其他邮箱（未测试，仅供参考）**

在对应邮箱设置中开启 IMAP/SMTP，获取授权码或应用密码，并修改服务器地址，例如：

| 邮箱 | imap_server | smtp_server |
|------|-------------|-------------|
| 163 | imap.163.com | smtp.163.com |
| Gmail | imap.gmail.com | smtp.gmail.com |
| Outlook | outlook.office365.com | smtp.office365.com |

端口通常为 IMAP 993、SMTP 465（SSL）。具体以邮箱服务商说明为准。

## 运行

```bash
python3 main.py
```

在 OpenClaw 中：`python3 {baseDir}/main.py`

## 可选配置

`config.json` 的 `analysis` 段：

| 字段 | 说明 | 默认 |
|------|------|------|
| `mailbox_name` | IMAP 文件夹，如 `网上购票` | 全邮箱搜索 |
| `max_emails` | 最大读取封数 | 10000 |
| `start_year` / `end_year` | 统计年份范围 | 不限 |

`mailbox_name` 文件夹名因邮箱而异；QQ 邮箱常用 `网上购票`。

## 故障排查

| 现象 | 处理 |
|------|------|
| 提示邮箱未配置 | 按报错中的路径编辑 `config.json` |
| IMAP 连接失败 | 确认授权码正确、IMAP 已开启 |
| 邮件很少 | 设置 `analysis.mailbox_name` 为 `网上购票` |

## 参考

- 技术细节见 [TECHNICAL.md](TECHNICAL.md)
