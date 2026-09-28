/**
 * 配置解析（与 src/mcp_server.py 对应）。
 *
 * 配置来源（优先级从高到低）：
 * 1. 环境变量 MAIL12306_* —— 由 ZCode 客户端从插件 userConfig 展开注入。
 * 2. 用户配置文件 ~/.zcode/mail-analysis-12306/config.json（save_mail_config 写入）。
 */

import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** 由构建脚本 esbuild define 注入的仓库根目录绝对路径。 */
declare const __REPO_ROOT__: string;

export interface EmailConfig {
  sender_email: string;
  sender_password: string;
  recipient_email: string[];
}

export interface MailConfig {
  email?: Partial<EmailConfig>;
  imap_server?: string;
  imap_port?: number;
  smtp_server?: string;
  smtp_port?: number;
  analysis?: {
    mailbox_name?: string | null;
    max_emails?: number;
    start_year?: number | null;
    end_year?: number | null;
    start_month?: string | null;
    end_month?: string | null;
  };
  [key: string]: unknown;
}

/** 当前产物（bundle）所在目录，等价于 Python 的 __file__ 目录。 */
export const BUNDLE_DIR = dirname(fileURLToPath(import.meta.url));

/** 仓库根目录：构建时由 esbuild define 注入；本地 ts 直跑时回退到 dist/ 上两级。 */
export const REPO_ROOT =
  typeof __REPO_ROOT__ === "string" ? __REPO_ROOT__ : join(BUNDLE_DIR, "..", "..");

export const CONFIG_DIR =
  process.env.MAIL12306_CONFIG_DIR || join(homedir(), ".zcode", "mail-analysis-12306");

export const CONFIG_PATH = process.env.MAIL12306_CONFIG || join(CONFIG_DIR, "config.json");

export const RUN_CONFIG_PATH = join(CONFIG_DIR, "run-config.json");
export const RUN_LOG_PATH = join(CONFIG_DIR, "run.log");

export const TERMINAL_MARKERS = [
  "所有任务完成",
  "邮件发送失败",
  "程序运行出错",
  "邮箱尚未配置",
  "无法连接到邮箱服务器",
  "未找到任何12306相关邮件",
  "未能从邮件中提取到任何票务记录",
  "分析报告为空",
  "用户中断程序",
];

export const SERVER_INFO = { name: "mail-analysis-12306", version: "0.7.0" };

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const ENV_FOR: Record<string, string> = {
  sender_email: "MAIL12306_SENDER_EMAIL",
  sender_password: "MAIL12306_SENDER_PASSWORD",
  recipient_email: "MAIL12306_RECIPIENT_EMAIL",
  imap_server: "MAIL12306_IMAP_SERVER",
  smtp_server: "MAIL12306_SMTP_SERVER",
  imap_port: "MAIL12306_IMAP_PORT",
  smtp_port: "MAIL12306_SMTP_PORT",
  mailbox_name: "MAIL12306_MAILBOX_NAME",
};

export const UI_HINT =
  "设置 → 插件管理 → 12306邮件分析 → 详情 → 高级设置（Advanced），填写邮箱地址、授权码、报告收件人后重启会话";

export function isPlaceholder(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === "string") {
    const s = value.trim();
    return !s || s.startsWith("your_") || s.endsWith("@example.com");
  }
  return false;
}

export function getEnv(key: string): string | null {
  const raw = (process.env[ENV_FOR[key]] || "").trim();
  if (!raw) return null;
  // 其他 agent 不会展开 ${user_config.*} 模板，字面量模板值按未配置处理，回退配置文件。
  if (raw.startsWith("${") && raw.endsWith("}") && raw.includes("user_config")) {
    return null;
  }
  return raw;
}

export function loadFileConfig(): MailConfig | null {
  if (!existsSync(CONFIG_PATH)) return null;
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf-8")) as MailConfig;
  } catch {
    return null;
  }
}

export function effectiveConfig(): MailConfig {
  const cfg: MailConfig = loadFileConfig() || {};
  const email = (cfg.email = cfg.email || {});

  const envEmail = getEnv("sender_email");
  if (envEmail) email.sender_email = envEmail;
  const envPw = getEnv("sender_password");
  if (envPw) email.sender_password = envPw;
  const envRecv = getEnv("recipient_email");
  if (envRecv) {
    email.recipient_email = envRecv
      .split(/[,;]/)
      .map((r) => r.trim())
      .filter(Boolean);
  }
  if (getEnv("imap_server")) cfg.imap_server = getEnv("imap_server")!;
  if (getEnv("smtp_server")) cfg.smtp_server = getEnv("smtp_server")!;
  for (const portKey of ["imap_port", "smtp_port"] as const) {
    const raw = getEnv(portKey);
    if (raw) {
      const n = parseInt(raw, 10);
      if (!Number.isNaN(n)) cfg[portKey] = n;
    }
  }
  if (getEnv("mailbox_name")) {
    cfg.analysis = cfg.analysis || {};
    cfg.analysis.mailbox_name = getEnv("mailbox_name");
  }
  return cfg;
}

export function configSource(): string {
  if (getEnv("sender_email") || getEnv("sender_password") || getEnv("recipient_email")) {
    return "plugin_settings";
  }
  if (loadFileConfig()) return "config_file";
  return "none";
}

export function missingFields(config: MailConfig | null): string[] {
  const missing: string[] = [];
  const emailCfg = (config || {}).email || {};
  if (isPlaceholder(emailCfg.sender_email)) missing.push("email.sender_email");
  if (isPlaceholder(emailCfg.sender_password)) missing.push("email.sender_password");
  let recipients: string | string[] | undefined = emailCfg.recipient_email;
  if (Array.isArray(recipients)) recipients = recipients[0] ?? null;
  if (isPlaceholder(recipients)) missing.push("email.recipient_email");
  return missing;
}

export function saveFileConfig(config: MailConfig): void {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");
}

export function recipientListToString(recipients: unknown): string {
  if (Array.isArray(recipients)) {
    return recipients.filter((r): r is string => typeof r === "string").join(", ");
  }
  return "";
}
