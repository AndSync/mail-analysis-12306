# 快速开始指南

## 第一步：确认Python版本

确保您的 Python 版本 >= 3.6

```bash
python --version
```

**无需安装任何依赖！** 本项目仅使用Python标准库。

## 第二步：配置邮箱

编辑 `config.json` 文件，修改以下配置：

### QQ邮箱用户（已预配置）

如果您的12306邮件在QQ邮箱中，只需修改授权码：

```json
{
  "email": {
    "sender_email": "970974380@qq.com",
    "sender_password": "您的授权码",  // ← 修改这里
    "recipient_email": ["781408677@qq.com"]
  }
}
```

**获取QQ邮箱授权码：**
1. 登录 https://mail.qq.com
2. 点击顶部"设置" → "账户"
3. 找到"POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务"
4. 确保"IMAP/SMTP服务"已开启
5. 点击"生成授权码"
6. 按提示发送短信，获取授权码
7. 将授权码填入配置文件

### 其他邮箱用户

需要修改服务器配置：

**163邮箱：**
```json
{
  "imap_server": "imap.163.com",
  "imap_port": 993,
  "smtp_server": "smtp.163.com",
  "smtp_port": 465
}
```

**Gmail：**
```json
{
  "imap_server": "imap.gmail.com",
  "imap_port": 993,
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 465
}
```

## 第三步：确认邮箱文件夹名称

查看您的12306邮件在哪个文件夹：
- 如果在收件箱根目录：保持 `"mailbox_name": "INBOX"`
- 如果在“12306”文件夹：改为 `"mailbox_name": "12306"` 或 `"INBOX.12306"`

## 第四步：（可选）设置统计范围

如果只想统计特定年份：

```json
"analysis": {
  "start_year": 2020,
  "end_year": 2024
}
```

如果统计全部，保持 `null` 即可。

## 第五步：运行程序

```bash
python main.py
```

程序会自动执行以下步骤：
1. ✅ 连接邮箱
2. ✅ 读取12306邮件
3. ✅ 解析票务信息
4. ✅ 分析数据
5. ✅ 生成HTML报告
6. ✅ 发送邮件

## 查看结果

### 方式一：查收邮件
报告会发送到配置的收件人邮箱，直接在手机或电脑上查看。

### 方式二：本地文件
程序会在当前目录生成HTML文件：
```
12306_report_20260427_143022.html
```
双击即可在浏览器中打开。

## 常见问题速查

### ❌ 连接失败
- 检查授权码是否正确（不是登录密码）
- 确认IMAP服务已开启
- 检查网络连接

### ❌ 找不到邮件
- 确认 `mailbox_name` 是否正确
- 尝试改为 `"INBOX"` 测试
- 检查邮箱中是否有12306邮件

### ❌ 解析数据少
- 查看 `analysis.log` 日志文件
- 12306邮件格式可能有所变化
- 部分老旧邮件可能格式不同

### ❌ 邮件发送失败
- 检查SMTP配置
- 确认授权码有效
- 查看日志文件错误信息

## 需要帮助？

查看详细文档：[README.md](README.md)
查看运行日志：`analysis.log`

---

**祝您旅途愉快！🚄✨**
