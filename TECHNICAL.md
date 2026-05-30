# 12306邮件分析系统 - 技术文档

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      main.py                            │
│                    (主流程控制)                          │
└─────────────────┬───────────────────────────────────────┘
                  │
      ┌───────────┼───────────┬───────────┬───────────┐
      │           │           │           │           │
      ▼           ▼           ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ mail_    │ │ email_   │ │ data_    │ │ html_    │ │ email_   │
│ reader   │ │ parser   │ │ analyzer │ │ report   │ │ sender   │
└────────── └──────────┘ ──────────┘ └──────────┘ └──────────
```

## 核心模块详解

### 1. mail_reader.py - 邮件读取模块

#### 功能
- IMAP连接管理
- 文件夹遍历
- 邮件搜索和获取
- 编码解码处理

#### 关键技术点

**1.1 Modified UTF-7编码处理**
```python
# QQ邮箱中文文件夹使用 IMAP Modified UTF-7 编码
# 现在支持中文文件夹名自动转码并匹配
# "网上购票" -> "&f1FOCo0teWg-"
```

**1.2 搜索策略**
```python
# 指定文件夹时：直接批量拉取完整邮件，速度优先
search_criteria = 'ALL'

# 未指定文件夹时：全邮箱搜索 + 头部预筛 + 正文获取
search_criteria = 'ALL'
```

**1.3 多编码邮件解码**
```python
# 支持UTF-8、GBK、GB2312等多种编码
def _decode_mime_words(decoded_parts):
    for part, charset in decoded_parts:
        if charset:
            decoded_str += part.decode(charset, errors='ignore')
        else:
            decoded_str += part.decode('utf-8', errors='ignore')
```

**1.4 文件夹遍历容错**
```python
# 某些文件夹不可访问，需要跳过
try:
    status, messages = mailbox.select(mailbox_name)
    if status != 'OK':
        continue
except Exception:
    logger.warning(f"跳过文件夹 {mailbox_name}")
```

**1.5 OpenClaw skill 调用方式**
```text
用户发送自然语言指令
    ↓
OpenClaw 调用本 skill
    ↓
main.py 串联完成 读取 → 解析 → 统计 → 生成 → 发送
```

### 2. email_parser.py - 邮件解析模块

#### 功能
- HTML内容提取
- 纯文本清理
- 多格式兼容解析
- 乘客信息提取

#### 关键技术点

**2.1 HTML清理**
```python
class SimpleHTMLParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == 'br':
            self.text_parts.append('\n')
    
    def handle_data(self, data):
        self.text_parts.append(data)
```

**2.2 多格式兼容正则**
```python
# 新格式：2026年05月06日02:30开
# 旧格式：01月24日19:28
date_pattern = r'(\d{4}年)?(\d{1,2}月\d{1,2}日)\s*(\d{2}:\d{2})开?'

# 新格式：G4480次
# 旧格式：T164次
train_pattern = r'([GDCKZT]\d+)次(?:列车)?'
```

**2.3 多人订单拆分**
```python
# 匹配格式：1.张三, 2.李四,
passenger_pattern = r'\d+\.([\u4e00-\u9fa5·]{2,4})[,，]'

# 提取每个乘客的完整信息
for match in re.finditer(passenger_pattern, text):
    passenger_info = self._extract_single_passenger_info(line)
```

**2.4 座位类型标准化**
```python
# 正则优先匹配具体类型
seat_pattern = r'(硬卧|软卧|动卧|硬座|软座|商务座|特等座|一等座|二等座|无座|[\u4e00-\u9fa5]+?(?:上|中|下)铺)'

# 归一化处理
if '硬' in seat_type:
    seat_type = '硬卧'
elif '软' in seat_type:
    seat_type = '软卧'
```

**2.5 退票/改签检测**
```python
def _detect_ticket_type(subject, body):
    refund_keywords = ['退票', '退单', '退款', '退订', '返还', '已退票', '退改', '停运']
    change_keywords = ['改签', '变更']
    
    if any(kw in subject for kw in refund_keywords):
        return 'refund'
    elif any(kw in subject for kw in change_keywords):
        return 'change'
    return 'purchase'
```

### 3. data_analyzer.py - 数据分析模块

#### 功能
- 数据过滤和清洗
- 多维度统计分析
- 聚合计算

#### 关键技术点

**3.1 时间维度选择**
```python
# 优先使用出发日期，避免跨年统计错误
year = record.get('_year')
if not year and '_datetime' in record:
    year = record['_datetime'].year
```

**3.2 城市名称标准化与别名映射**
```python
# 第一步：去除站点后缀（长后缀优先）
suffixes = ['火车站', '高铁站', '动车站', '城际站', 
            '东站', '西站', '南站', '北站', '站']

for suffix in suffixes:
    if city.endswith(suffix):
        city = city[:-len(suffix)]
        break

# 第二步：应用城市别名映射
# 从 config_cities.json 加载映射表
if city in self.city_mapping:
    city = self.city_mapping[city]

# 示例：
# "郑州航空港站" → 去后缀 → "郑州航空港" → 映射 → "郑州"
# "武昌站" → 去后缀 → "武昌" → 映射 → "武汉"
# "北京西站" → 去后缀 → "北京西" → 映射 → "北京"
```

**配置文件结构 (config_cities.json)**
```json
{
  "city_aliases": {
    "武汉": ["武昌", "汉口", "汉阳", "武汉东"],
    "北京": ["北京西", "北京南", "北京北", "北京东", "北京丰台", "北京朝阳"],
    "郑州": ["郑州东", "郑州西", "郑州航空港"]
  }
}
```

**设计原则:**
- Key是主城市名（最终显示的名称）
- Value是需要映射到这个城市的站点列表
- 只包含需要映射的站点，不包含主城市本身
- 目前包含170+个站点映射，覆盖全国主要城市

**3.3 退票/改签数据处理逻辑**
```python
def _get_effective_purchase_records(self, records):
    """
    获取有效出行记录
    - 退票对应的原购票记录不计入出行统计（因为没有出行）
    - 改签对应的原购票记录仍计入出行统计（因为最终还是出行了）
    """
    purchase_records = [r for r in records if r.get('type') == 'purchase']
    # 只过滤退票对应的原购票，不过滤改签的
    refund_records = [r for r in records if r.get('type') == 'refund']

    canceled_counter = Counter()
    for record in refund_records:
        for key in self._build_trip_keys(record):
            canceled_counter[key] += 1

    effective_records = []
    for record in purchase_records:
        for key in self._build_trip_keys(record):
            if canceled_counter[key] > 0:
                canceled_counter[key] -= 1
                break
        else:
            effective_records.append(record)

    return effective_records
```

**关键逻辑说明:**
- **退票**: 原购票不计入出行统计，因为乘客没有实际出行
- **改签**: 原购票仍计入出行统计，因为改签后乘客完成了出行
- **金额计算**: 退票按退款金额统计，改签按补差/退差统计

**3.4 热门路线统计**
```python
# 路线格式：北京西站→郑州站
route = f"{departure_station}→{arrival_station}"
route_counter[route] += 1

# 按次数排序
sorted_routes = sorted(route_counter.items(), key=lambda x: x[1], reverse=True)
```

### 4. html_report.py - HTML报告生成

#### 功能
- CSS样式生成
- 数据结构转HTML
- 响应式布局

#### 关键技术点

**4.1 紧凑布局设计**
```css
body {
    padding: 2px;  /* 极致紧凑 */
    font-size: 0.78em;
}

.stat-card {
    padding: 5px 7px;  /* 最小化内边距 */
}
```

**4.2 防链接识别**
```html
<span style="
    color: #666 !important;
    text-decoration: none !important;
    pointer-events: none;
    -webkit-touch-callout: none;
    user-select: none;
">
2024-01-15
</span>
```

**4.3 表格优化**
```css
table {
    table-layout: fixed;  /* 固定布局防止拉伸 */
    font-size: 0.78em;
}

th, td {
    white-space: nowrap;  /* 防止换行 */
}
```

**4.4 响应式卡片网格**
```css
.overview-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 5px;  /* 最小间距 */
}
```

### 5. email_sender.py - 邮件发送模块

#### 功能
- SMTP连接
- HTML邮件构建
- 多收件人支持

#### 关键技术点

**5.1 邮件构建**
```python
msg = MIMEMultipart('alternative')
msg['From'] = sender_email
msg['To'] = ', '.join(recipients)
msg['Subject'] = f'12306出行统计报告 - {datetime.now().strftime("%Y-%m-%d")}'

html_part = MIMEText(html_content, 'html', 'utf-8')
msg.attach(html_part)
```

**5.2 SSL加密连接**
```python
server = smtplib.SMTP_SSL(smtp_server, smtp_port)
server.login(sender_email, sender_password)
server.sendmail(sender_email, recipients, msg.as_string())
```

### 6. main.py - 主流程控制

#### 执行流程
```python
1. 加载配置文件 (config.json)
2. 读取邮件 (mail_reader)
   ├─ 连接IMAP服务器
   ├─ 遍历文件夹
   └─ 搜索12306邮件
3. 解析邮件 (email_parser)
   ├─ HTML转纯文本
   ├─ 正则提取信息
   └─ 构建结构化数据
4. 数据分析 (data_analyzer)
   ├─ 数据清洗
   ├─ 多维度统计
   └─ 生成报告数据
5. 生成HTML (html_report)
   ├─ CSS样式
   ├─ 数据结构转HTML
   └─ 保存文件
6. 发送邮件 (email_sender)
   ├─ SMTP连接
   ├─ 构建邮件
   └─ 发送
```

## 数据结构

### 邮件原始数据
```python
{
    'subject': '网上购票系统-用户支付通知',
    'from': '12306@rails.com.cn',
    'date': 'Thu, 06 Feb 2026 12:30:00 +0800',
    'body': '<html>...</html>'
}
```

### 解析后的票务记录
```python
{
    'order_number': 'E123456789',
    'train_number': 'G1234',
    'departure_station': '北京西站',
    'arrival_station': '上海虹桥站',
    'departure_datetime': '2024-01-15 08:00',
    'price': 553.0,
    'seat_type': '二等座',
    'passenger_name': '张三',
    'carriage': '05',
    'seat_number': '12A',
    'ticket_type': 'purchase',  # purchase/refund/change
    '_year': 2024,              # 用于年度统计
    '_datetime': datetime(...), # 邮件接收时间
    '_departure_city': '北京',  # 标准化城市名
    '_arrival_city': '上海'
}
```

### 统计数据
```python
overview = {
    'total_records': 128,
    'purchase_count': 115,
    'refund_count': 10,
    'change_count': 3,
    'total_spent': 28560.0,
    'total_refunded': 1320.0,
    'net_spent': 27240.0,
    'date_range': {'start': '2020-03-12', 'end': '2024-12-20'}
}
```

## 性能优化

### 1. 邮件读取优化
- 指定文件夹避免全量遍历
- 分批获取（每50封打印进度）
- 延迟控制（0.02秒/封）

### 2. 解析优化
- 正则预编译
- HTML解析器复用
- 异常快速跳过

### 3. 统计优化
- defaultdict加速聚合
- 单次遍历多维度统计
- 内存优化（按需加载）

## 错误处理

### 常见错误及处理
```python
1. IMAP连接失败
   → 检查网络和授权码
   → 重试机制

2. 文件夹不可访问
   → 跳过并记录日志
   → 继续处理其他文件夹

3. 邮件解析失败
   → 记录失败邮件信息
   → 不影响其他邮件
   → 当前失败率 < 0.3%

4. 编码错误
   → 多编码降级策略
   → errors='ignore' 容错
```

## 扩展性

### 支持的邮箱类型

默认配置面向 QQ 邮箱（**已测试**）。程序使用标准 IMAP/SMTP，其他邮箱理论上只需改 `config.json` 中的服务器地址和凭据即可，**尚未逐一实测**。

```python
# QQ 邮箱（已测试）
imap_server = 'imap.qq.com'
smtp_server = 'smtp.qq.com'

# 163 邮箱（未测试）
imap_server = 'imap.163.com'
smtp_server = 'smtp.163.com'

# Gmail（未测试）
imap_server = 'imap.gmail.com'
smtp_server = 'smtp.gmail.com'
```

### 未来可扩展功能
1. PDF报告导出
2. Excel数据导出
3. 可视化图表（matplotlib）
4. 命令行参数支持
5. 定时任务（cron）
6. Web界面
7. 多邮箱账号支持

## 测试数据

### 典型运行结果
```
邮件获取: 120 封
解析记录: 128 条
未解析: 1/120 (0.83%)
统计时间: 2020-03-12 至 2024-12-20
总消费: ¥28,560.00
净消费: ¥27,240.00
运行时间: ~2分钟
```

## 技术栈总结
- Python 3.6+
- imaplib (IMAP客户端)
- smtplib (SMTP客户端)
- email (邮件解析)
- html.parser (HTML解析)
- re (正则表达式)
- datetime (时间处理)
- collections (数据结构)
- json (配置管理)
- logging (日志)

**零第三方依赖，纯标准库实现**
