# 12306 邮件分析系统 - 技术文档

从邮箱读取 12306 购票/退票/改签邮件，生成 HTML 出行统计报告并发送到指定邮箱。Node.js（TypeScript）实现，esbuild 打单文件，安装即用。

## 系统架构

```
                ┌─────────────────────────────────────────┐
                │            入口层                        │
                │  cli.ts (CLI)   │  server.ts (MCP)       │
                └───────────────┬─────────────────────────┘
                                │
     ┌──────────┬──────────┬────┴─────┬──────────┬──────────┐
     ▼          ▼          ▼          ▼          ▼          ▼
┌─────────┐┌──────────┐┌───────────┐┌──────────┐┌──────────┐
│ mail_   ││ email_   ││ data_     ││ html_    ││ email_   │
│ reader  ││ parser   ││ analyzer  ││ report   ││ sender   │
│ (IMAP)  ││ (解析)   ││ (统计)    ││ (报告)   ││ (SMTP)   │
└─────────┘└──────────┘└───────────┘└──────────┘└──────────┘
```

- `src/cli.ts`：CLI 主流程（读 → 解析 → 统计 → 生成 → 发送），支持 `--config` 与 `MAIL12306_CONFIG` 环境变量。
- `src/mcp/server.ts`：stdio JSON-RPC MCP 服务器，提供 4 个工具，未配置邮箱时对分析工具做硬性门禁。
- `src/lib/`：核心业务逻辑，与入口层解耦，可被 CLI、MCP 或其他 agent 复用。

## 构建产物

- `dist/mcp/server.js`：MCP 服务器入口（esbuild 单文件 bundle）。
- `dist/cli.js`：后台分析管线入口（MCP 后台分离进程调用它）。
- 依赖全部 bundle 进产物（imapflow/mailparser/nodemailer/@modelcontextprotocol/sdk），安装无需 `npm install`。

## 核心模块

### 1. mailReader.ts — 邮件读取

- IMAP 连接管理、文件夹遍历、搜索与批量获取（底层 imapflow）。
- **Modified UTF-7 编码**：QQ 邮箱中文文件夹（如「网上购票」）用 IMAP Modified UTF-7 编码，读取时自动解码并按中文名匹配。
- **搜索策略**：指定 `mailbox_name` 时直读该文件夹（速度优先）；否则扫描全邮箱后本地筛 12306 邮件。

### 2. emailParser.ts — 邮件解析

- HTML 转纯文本、多编码解码。
- 多格式兼容：新格式（`2026年05月06日02:30开`、`G4480次`）与旧格式（`01月24日19:28`、`T164次`）。
- 多人订单按「`1.姓名，`」序号行拆分为多条记录，**每张票的票价即实付**（避免多人邮件把最后一张票价当全单实付）。
- 类型检测：主题/正文关键词区分 purchase / refund / change；「候补订单退单通知」排除（未出票，不算购票/退票）。
- 金额字段：退票费 `refund_fee`、实退票款 `actual_refund_amount`、改签补差/退差。改签邮件若明确写了「实退票款」，标记 `_has_explicit_refund`。

### 3. dataAnalyzer.ts — 数据分析

核心：`_getEffectivePurchaseRecords` 计算**有效行程**（真实乘坐）：

- 退票对应的原购票不计入（未出行）。
- 改签对应的原购票被改签后新票取代。
- 乱序到达（退票邮件早于购票邮件）用两遍抵消 + pending 机制处理。
- 最终按冲突键消解「同一乘客同一时刻同车同路线」的重复记录。

**金额口径**：

| 指标 | 计算 |
|------|------|
| 消费总额 | 购票实付 + 改签补差 − 改签退差 − 退票退款 |
| 退票手续费 | 各笔退票 `refund_fee`（同订单同乘客去重）之和 |
| 改签手续费 | 改签为低票价时，(原票面 − 新票面) − 实退金额；仅统计有 `_has_explicit_refund` 的新格式邮件 |
| 退改扣费 | 退票手续费 + 改签手续费 |

**改签补差/退差推算**：改签邮件常只写「新车票票款共计」不写补收/退差，按 `(订单, 乘客)` 匹配原票票面推算「新票面 − 原票面」。

**城市归并**：站点名先剥后缀（东/西/南/北站等），再经 `config_cities.json` 的 `city_aliases` 映射到主城市（如 武昌→武汉、八达岭长城→北京）。同城行程（出发城市 == 到达城市）不计入出发/到达城市次数。

### 4. htmlReport.ts — HTML 报告

- 邮件兼容的表格布局（`table-layout: fixed` + 表头 `bgcolor` + 防链接识别）。
- 概览 6 卡：出行次数 / 退票记录 / 改签记录 / 消费总额 / 退改扣费 / 平均票价。
- 各表分维度金额列：聚合类（年度/乘客/列车/路线）用消费总额，分布类（城市/座位）用平均票价，出发时间无金额。
- 列表最多 10 条，同次数按最近乘坐时间降序排列。

### 5. emailSender.ts — 邮件发送

- SMTP（SSL 465）连接、HTML 邮件、单/多收件人（底层 nodemailer）。

### 6. server.ts — MCP 服务器

- stdio JSON-RPC（initialize / tools/list / tools/call / ping）。
- 配置来源优先级：环境变量（ZCode 的 `${user_config.*}` 注入）> 用户配置文件 `~/.zcode/mail-analysis-12306/config.json`。
- `analyze_12306_mail` 后台启动（detached 子进程，日志写 `run.log`），`get_analysis_status` 轮询结果——避免长任务阻塞 MCP 调用超时。
- 未展开的 `${user_config.*}` 字面量（其他 agent 不展开模板）按未配置处理，回退配置文件。

## 数据结构

### 解析后的票务记录（emailParser 输出）

```json
{
    "type": "purchase",
    "order_number": "E123456789",
    "passenger_name": "张三",
    "train_number": "G1234",
    "departure_station": "北京西站",
    "arrival_station": "上海虹桥站",
    "departure_datetime": "2024-01-15 08:00",
    "price": 553.0,
    "actual_spent_amount": 553.0,
    "actual_refund_amount": null,
    "refund_fee": null,
    "seat_type": "二等座",
    "date": "2024-01-10 12:00:00"
}
```

### 报告数据（dataAnalyzer 输出）

```json
{
    "overview": {
        "purchase_count": 355,
        "refund_count": 123,
        "change_count": 73,
        "net_spent": 65754.5,
        "refund_fee_total": 1379.0,
        "change_fee_total": 110.0,
        "refund_change_fee": 1489.0,
        "avg_ticket_price": 191.28
    },
    "yearly_stats": [],
    "popular_cities": { "departures": [], "arrivals": [], "routes": [] },
    "popular_trains": [],
    "seat_type_stats": [],
    "passenger_stats": [],
    "departure_time_ranking": []
}
```

## 性能

- 指定 `mailbox_name` 直读，避免全邮箱遍历。
- 分批获取正文（每 40 封打进度），加延迟避免触发邮箱限流。
- 单次遍历多维度统计，Map 聚合。

## 错误处理

| 错误 | 处理 |
|------|------|
| IMAP 连接失败 | 打印服务器/授权码提示，退出 |
| 文件夹不可访问 | 跳过并记录，继续其他文件夹 |
| 单封邮件解析失败 | 记录主题与原因，不影响整体 |
| 编码错误 | mailparser 多编码解码 + 容错 |

## 邮箱支持

默认面向 QQ 邮箱（已实测）。程序使用标准 IMAP/SMTP，其他邮箱改 `config.json` 的服务器地址与凭据即可，尚未逐一实测：

| 邮箱 | IMAP | SMTP |
|------|------|------|
| QQ（已测试） | imap.qq.com | smtp.qq.com |
| 163 | imap.163.com | smtp.163.com |
| Gmail | imap.gmail.com | smtp.gmail.com |
| Outlook | outlook.office365.com | smtp.office365.com |

## 技术栈

Node.js 18+ / TypeScript。运行时依赖：imapflow、mailparser、nodemailer、@modelcontextprotocol/sdk、zod；构建：esbuild。
