# 配置示例说明

## config.json 完整配置项

```json
{
  // 邮箱配置
  "email": {
    // 发件人邮箱地址（用于读取邮件和发送报告）
    "sender_email": "your_email@qq.com",
    
    // 邮箱授权码（注意：不是登录密码！）
    // QQ邮箱获取方式：设置 → 账户 → 生成授权码
    "sender_password": "your_authorization_code",
    
    // 收件人列表（可以填写多个邮箱）
    "recipient_email": [
      "recipient1@qq.com",
      "recipient2@163.com"
    ]
  },
  
  // IMAP服务器配置（用于读取邮件）
  "imap_server": "imap.qq.com",
  "imap_port": 993,
  
  // SMTP服务器配置（用于发送邮件）
  "smtp_server": "smtp.qq.com",
  "smtp_port": 465,
  
  // 分析配置
  "analysis": {
    // 12306邮件所在的邮箱文件夹名称
    // 常见值：
    // - "INBOX" : 收件箱根目录
    // - "12306" : 名为12306的文件夹
    // - "INBOX.12306" : 收件箱下的12306子文件夹
    "mailbox_name": "INBOX.12306",
    
    // 最大处理邮件数量（防止处理过多邮件导致时间过长）
    "max_emails": 10000,
    
    // 统计开始年份（null表示不限制，从最早开始）
    "start_year": null,
    
    // 统计结束年份（null表示不限制，到最新）
    "end_year": null,
    
    // 统计开始月份（格式："YYYY-MM"，例如："2020-01"）
    "start_month": null,
    
    // 统计结束月份（格式："YYYY-MM"，例如："2024-12"）
    "end_month": null
  }
}
```

## 常用邮箱服务器配置

### QQ邮箱
```json
{
  "imap_server": "imap.qq.com",
  "imap_port": 993,
  "smtp_server": "smtp.qq.com",
  "smtp_port": 465
}
```

### 163邮箱
```json
{
  "imap_server": "imap.163.com",
  "imap_port": 993,
  "smtp_server": "smtp.163.com",
  "smtp_port": 465
}
```

### 126邮箱
```json
{
  "imap_server": "imap.126.com",
  "imap_port": 993,
  "smtp_server": "smtp.126.com",
  "smtp_port": 465
}
```

### Gmail
```json
{
  "imap_server": "imap.gmail.com",
  "imap_port": 993,
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 465
}
```
注意：Gmail需要开启"不够安全的应用访问权限"或使用应用专用密码

### Outlook/Hotmail
```json
{
  "imap_server": "outlook.office365.com",
  "imap_port": 993,
  "smtp_server": "smtp.office365.com",
  "smtp_port": 587
}
```

## 配置场景示例

### 场景1：统计所有年份的全部数据
```json
"analysis": {
  "mailbox_name": "INBOX",
  "max_emails": 10000,
  "start_year": null,
  "end_year": null,
  "start_month": null,
  "end_month": null
}
```

### 场景2：只统计2020-2024年的数据
```json
"analysis": {
  "mailbox_name": "INBOX",
  "max_emails": 10000,
  "start_year": 2020,
  "end_year": 2024,
  "start_month": null,
  "end_month": null
}
```

### 场景3：统计2023年全年的数据
```json
"analysis": {
  "mailbox_name": "INBOX",
  "max_emails": 10000,
  "start_year": 2023,
  "end_year": 2023,
  "start_month": null,
  "end_month": null
}
```

### 场景4：统计2023年1月到6月的数据
```json
"analysis": {
  "mailbox_name": "INBOX",
  "max_emails": 10000,
  "start_year": null,
  "end_year": null,
  "start_month": "2023-01",
  "end_month": "2023-06"
}
```

### 场景5：邮件在特定的"12306"文件夹中
```json
"analysis": {
  "mailbox_name": "12306",
  "max_emails": 5000,
  "start_year": null,
  "end_year": null,
  "start_month": null,
  "end_month": null
}
```

## 重要提示

⚠️ **安全提醒**
1. `config.json` 包含敏感信息（邮箱授权码），请勿分享给他人
2. 不要将 `config.json` 提交到公开的代码仓库
3. `.gitignore` 已配置忽略该文件，使用Git时会自动排除

📧 **邮箱授权码 vs 登录密码**
- 授权码是专门用于第三方客户端访问邮箱的密码
- 授权码比登录密码更安全，可以随时撤销
- 授权码通常是一串随机字符，如：`abcd efgh ijkl mnop`

📂 **邮箱文件夹名称**
- 不同邮箱客户端显示的文件夹名称可能不同
- QQ邮箱网页版中，文件夹层级用 "." 分隔
- 如果不确定，可以先尝试 "INBOX"

🔍 **如何查看文件夹名称**
1. 登录邮箱网页版
2. 查看左侧文件夹列表
3. 右键点击文件夹，查看属性或URL
4. 或在程序中先使用 "INBOX" 测试

---

如有其他问题，请查看 README.md 或 QUICKSTART.md
