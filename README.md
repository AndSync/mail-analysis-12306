# 12306邮件分析系统

一个强大的Python工具，用于分析您的12306购票邮件，生成详细的出行统计报告。

## 功能特点

✨ **核心功能**
- 📧 自动读取邮箱中的12306邮件
- 🔍 智能解析购票、退票、改签记录
- 📊 多维度数据分析统计
- 🎨 生成美观的HTML可视化报告
- 📬 自动将报告发送到指定邮箱

📈 **统计维度**
- ✅ 总体概览（总消费、购票次数、退票次数等）
- ✅ 年度统计（每年出行次数、消费金额）
- ✅ 热门城市（出发/到达城市TOP榜）
- ✅ 热门路线（最常走的路线）
- ✅ 常坐列车（乘坐频次最高的车次）
- ✅ 座位偏好（各类型座位选择统计）
- ✅ 乘客统计（多人出行的个人统计）
- ✅ 月度趋势（消费趋势分析）

## 安装依赖

**无需安装任何第三方库！**

本项目仅使用 Python 标准库，Python 3.6+ 即可直接运行。

```bash
# 直接运行，无需安装依赖
python main.py
```

## 配置说明

编辑 `config.json` 文件：

```json
{
  "email": {
    "sender_email": "your_email@qq.com",      // 发件人邮箱
    "sender_password": "your_auth_code",        // 邮箱授权码（非密码）
    "recipient_email": ["recipient@qq.com"]     // 收件人列表
  },
  "imap_server": "imap.qq.com",                 // IMAP服务器
  "imap_port": 993,                             // IMAP端口
  "smtp_server": "smtp.qq.com",                 // SMTP服务器
  "smtp_port": 465,                             // SMTP端口
  "analysis": {
    "mailbox_name": "INBOX.12306",              // 12306邮件所在文件夹
    "max_emails": 10000,                        // 最大处理邮件数
    "start_year": null,                         // 开始年份（null表示不限制）
    "end_year": null,                           // 结束年份
    "start_month": null,                        // 开始月份（格式："2020-01"）
    "end_month": null                           // 结束月份
  }
}
```

### 获取邮箱授权码

**QQ邮箱示例：**
1. 登录QQ邮箱网页版
2. 进入 设置 → 账户
3. 找到 POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务
4. 开启 IMAP/SMTP 服务
5. 生成授权码并填入配置文件

## 使用方法

### 基本使用

```bash
python main.py
```

程序会自动：
1. 连接邮箱并读取12306邮件
2. 解析所有票务记录
3. 进行数据分析
4. 生成HTML报告
5. 发送邮件到您的邮箱

### 按年份统计

修改 `config.json` 中的 `analysis` 部分：

```json
"analysis": {
  "start_year": 2020,
  "end_year": 2024
}
```

### 按月份统计

```json
"analysis": {
  "start_month": "2023-01",
  "end_month": "2023-12"
}
```

### 指定邮箱文件夹

如果您的12306邮件在特定文件夹中：

```json
"analysis": {
  "mailbox_name": "INBOX.12306"  // 或 "12306" 或其他文件夹名
}
```

## 输出结果

### 本地文件
- `12306_report_YYYYMMDD_HHMMSS.html` - HTML报告文件
- `analysis.log` - 运行日志

### 邮件内容
精美的HTML报告，包含：
- 渐变色卡片式概览统计
- 数据表格展示详细分析
- 响应式设计，支持手机查看

## 项目结构

```
mail-analysis/
├── main.py              # 主程序入口
├── config.json          # 配置文件
├── mail_reader.py       # 邮件读取模块
├── email_parser.py      # 邮件解析模块
├── data_analyzer.py     # 数据分析模块
├── html_report.py       # HTML报告生成模块
├── email_sender.py      # 邮件发送模块
├── requirements.txt     # Python依赖
└── README.md           # 说明文档
```

## 注意事项

⚠️ **重要提示**

1. **邮箱授权码**：配置文件中的密码是邮箱授权码，不是登录密码
2. **文件夹名称**：确保 `mailbox_name` 与实际邮箱文件夹名称一致
3. **网络连接**：需要稳定的网络连接来访问邮箱服务器
4. **处理时间**：如果邮件数量较多（几千封），可能需要几分钟时间
5. **数据准确性**：统计结果依赖于12306邮件的格式，如邮件格式变化可能影响解析

## 常见问题

### Q: 找不到12306邮件？
A: 检查以下几点：
- 确认 `mailbox_name` 是否正确
- 尝试使用 "INBOX" 作为文件夹名
- 确认邮箱中确实有12306邮件

### Q: 解析出的数据很少？
A: 可能原因：
- 12306邮件格式发生变化
- 邮件被识别为垃圾邮件
- 检查日志文件 `analysis.log` 查看详细错误

### Q: 邮件发送失败？
A: 检查：
- SMTP服务器配置是否正确
- 授权码是否有效
- 防火墙是否阻止了连接

### Q: 如何只统计特定年份？
A: 在 `config.json` 中设置 `start_year` 和 `end_year`

## 技术支持

如遇到问题，请查看 `analysis.log` 日志文件获取详细错误信息。

## 许可证

MIT License

---

**祝您使用愉快！🚄**
