/**
 * 后台分析管线。
 * 读取邮件 → 解析票务记录 → 统计分析 → 生成 HTML → SMTP 发送。
 *
 * 由 MCP 服务器以 detached 子进程方式启动，stdout 重定向到 run.log。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT, isPlaceholder } from "./lib/config.js";
import type { MailConfig } from "./lib/config.js";
import { MailReader } from "./lib/mailReader.js";
import { EmailParser } from "./lib/emailParser.js";
import { DataAnalyzer } from "./lib/dataAnalyzer.js";
import { HTMLReportGenerator } from "./lib/htmlReport.js";
import { EmailSender } from "./lib/emailSender.js";

const log = (...args: unknown[]) => {
  const ts = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${ts.getFullYear()}-${p(ts.getMonth() + 1)}-${p(ts.getDate())} ${p(ts.getHours())}:${p(ts.getMinutes())}:${p(ts.getSeconds())}`;
  console.log(`${stamp} - __main__ - INFO - ${args.map(String).join(" ")}`);
};

function resolveConfigPath(): string {
  const argv = process.argv.slice(2);
  const idx = argv.indexOf("--config");
  if (idx !== -1 && idx + 1 < argv.length) return argv[idx + 1];
  return process.env.MAIL12306_CONFIG || join(REPO_ROOT, "config", "config.json");
}

function loadConfig(configPath: string): MailConfig {
  const raw = readFileSync(configPath, "utf-8");
  return JSON.parse(raw) as MailConfig;
}

function validateConfig(config: MailConfig): boolean {
  const emailCfg = config.email || {};
  const missing: string[] = [];
  for (const key of ["sender_email", "sender_password", "recipient_email"] as const) {
    const value = emailCfg[key];
    if (key === "recipient_email") {
      if (!value || !Array.isArray(value) || !value[0]) missing.push(key);
      else if (isPlaceholder(value[0])) missing.push(key);
    } else if (isPlaceholder(value)) {
      missing.push(key);
    }
  }
  if (missing.length) {
    log(`邮箱尚未配置（缺少: ${missing.join(", ")}）`);
    return false;
  }
  return true;
}

async function main(): Promise<void> {
  log("=".repeat(60));
  log("12306邮件分析系统启动");
  log("=".repeat(60));

  const configPath = resolveConfigPath();
  const config = loadConfig(configPath);
  if (!validateConfig(config)) return;

  // 步骤1：读取邮件
  log("【步骤1】开始读取12306邮件...");
  const mailReader = new MailReader(config);
  if (!(await mailReader.connect())) {
    log("无法连接到邮箱服务器，程序退出");
    return;
  }

  let emailsData;
  let startYear: number | null = null;
  let endYear: number | null = null;
  let startMonth: string | null = null;
  let endMonth: string | null = null;
  try {
    let mailboxName = config.analysis?.mailbox_name ?? null;
    if (mailboxName === "") mailboxName = null;

    const analysisConfig = config.analysis || {};
    startYear = analysisConfig.start_year ?? null;
    endYear = analysisConfig.end_year ?? null;
    startMonth = analysisConfig.start_month ?? null;
    endMonth = analysisConfig.end_month ?? null;
    const maxEmails = analysisConfig.max_emails ?? 10000;

    let startDate: string | null = null;
    let endDate: string | null = null;

    if (startYear && startMonth) startDate = `01-${startMonth}-${startYear}`;
    else if (startYear) startDate = `01-Jan-${startYear}`;

    if (endYear && endMonth) {
      const mm = parseInt(String(endMonth).split("-")[1], 10) + 1;
      endDate = `01-${mm}-${String(endMonth).split("-")[0]}`;
    } else if (endYear) {
      endDate = `31-Dec-${endYear}`;
    }

    emailsData = await mailReader.search12306Emails(startDate, endDate, maxEmails, mailboxName);
  } finally {
    await mailReader.disconnect();
  }

  if (!emailsData || !emailsData.length) {
    log("未找到任何12306相关邮件");
    return;
  }
  log(`成功获取 ${emailsData.length} 封邮件`);

  // 步骤2：解析
  log("【步骤2】开始解析邮件内容...");
  const parser = new EmailParser();
  const records = parser.parseEmails(emailsData);
  if (!records.length) {
    log("未能从邮件中提取到任何票务记录");
    return;
  }
  log(`成功解析 ${records.length} 条票务记录`);

  // 步骤3：分析
  log("【步骤3】开始数据分析...");
  const analyzer = new DataAnalyzer(records);
  const reportData = analyzer.generateFullReport(startYear, endYear, startMonth, endMonth);
  if (!reportData || !Object.keys(reportData).length) {
    log("分析报告为空");
    return;
  }
  log("数据分析完成");

  // 步骤4：生成 HTML
  log("【步骤4】生成HTML报告...");
  const reportGenerator = new HTMLReportGenerator();
  const htmlContent = reportGenerator.generate(reportData as Record<string, any>);
  if (!htmlContent) {
    log("HTML报告生成失败");
    return;
  }
  log("HTML报告生成完成");

  // 步骤5：发送
  log("【步骤5】发送报告邮件...");
  const sender = new EmailSender(config);
  const subject = `12306出行统计报告 (${new Date().toISOString().slice(0, 10)})`;
  const success = await sender.sendReport(htmlContent, subject);

  if (success) {
    log("");
    log("=".repeat(60));
    log("✅ 所有任务完成！报告已发送到您的邮箱");
    log("=".repeat(60));
  } else {
    log("");
    log("=".repeat(60));
    log("❌ 邮件发送失败");
    log("=".repeat(60));
  }
}

main().catch((e) => {
  log(`程序运行出错: ${(e as Error).message}`);
  process.exit(1);
});
