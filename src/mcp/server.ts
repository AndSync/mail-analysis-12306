/**
 * ZCode MCP 服务器：12306 邮件分析（stdio，Node 实现）。
 * 4 个工具、env 优先级、后台分离进程、日志轮询。
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync, openSync, closeSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CONFIG_PATH,
  CONFIG_DIR,
  RUN_CONFIG_PATH,
  RUN_LOG_PATH,
  TERMINAL_MARKERS,
  SERVER_INFO,
  EMAIL_RE,
  UI_HINT,
  isPlaceholder,
  getEnv,
  loadFileConfig,
  effectiveConfig,
  configSource,
  missingFields,
  saveFileConfig,
  recipientListToString,
} from "../lib/config.js";
import type { MailConfig } from "../lib/config.js";

const BUNDLE_DIR = dirname(fileURLToPath(import.meta.url));
const CLI_JS = join(BUNDLE_DIR, "..", "cli.js");

const log = (msg: string) => {
  process.stderr.write(msg + "\n");
};

const TOOLS = [
  {
    name: "get_mail_config_status",
    description:
      "查看 12306 邮件分析的邮箱配置状态：是否已配置、配置来源（插件高级设置界面或配置文件）、缺少哪些字段、当前发件/收件邮箱与服务器地址（不会返回授权码）。",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "save_mail_config",
    description:
      "保存邮箱配置到用户配置文件（备用方式；首选是插件详情→高级设置的可视化界面）。" +
      "需要：sender_email（读取 12306 邮件的邮箱）、sender_password（IMAP/SMTP 授权码，非登录密码）、" +
      "recipient_email（报告收件人，单个邮箱字符串或列表）。可选：imap_server、imap_port、smtp_server、smtp_port、mailbox_name。" +
      "未提供服务器参数时默认 QQ 邮箱（imap.qq.com:993 / smtp.qq.com:465）。",
    inputSchema: {
      type: "object",
      properties: {
        sender_email: { type: "string", description: "邮箱地址" },
        sender_password: { type: "string", description: "IMAP/SMTP 授权码或应用专用密码" },
        recipient_email: {
          anyOf: [{ type: "string" }, { type: "array", items: { type: "string" } }],
          description: "报告收件人邮箱，可多个",
        },
        imap_server: { type: "string" },
        imap_port: { type: "integer" },
        smtp_server: { type: "string" },
        smtp_port: { type: "integer" },
        mailbox_name: { type: "string", description: 'IMAP 文件夹名，QQ 邮箱常用"网上购票"' },
      },
      required: ["sender_email", "sender_password", "recipient_email"],
    },
  },
  {
    name: "analyze_12306_mail",
    description:
      "后台启动 12306 邮件分析：读取邮箱中的 12306 购票/退票/改签邮件 → 解析票务记录 → 生成 HTML 出行统计报告 → 通过 SMTP 发送到收件人邮箱。" +
      "立即返回不等待完成，调用后请用 get_analysis_status 轮询进度和最终结果。邮箱未配置时直接拒绝执行并提示去插件高级设置界面配置。",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "get_analysis_status",
    description:
      "查看最近一次 12306 邮件分析任务的运行状态（运行中/已完成/已结束）与运行日志末尾。analyze_12306_mail 启动的是后台任务，用本工具轮询进度直到完成。",
    inputSchema: { type: "object", properties: {} },
  },
];

function toolGetStatus(): { text: string; isError: boolean } {
  const config = effectiveConfig();
  const emailCfg = config.email || {};
  const missing = missingFields(config);
  const text = JSON.stringify(
    {
      configured: missing.length === 0,
      source: configSource(),
      missing_fields: missing,
      config_file_path: CONFIG_PATH,
      sender_email: isPlaceholder(emailCfg.sender_email) ? null : emailCfg.sender_email,
      recipient_email: recipientListToString(emailCfg.recipient_email),
      imap_server: config.imap_server,
      smtp_server: config.smtp_server,
    },
    null,
    2
  );
  return { text, isError: false };
}

function toolSaveConfig(args: Record<string, unknown>): { text: string; isError: boolean } {
  const senderEmail = String(args.sender_email ?? "").trim();
  const senderPassword = args.sender_password ?? "";
  let recipientEmail: string[] | null = null;
  if (typeof args.recipient_email === "string") {
    recipientEmail = (args.recipient_email as string)
      .replace(/;/g, ",")
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean);
  } else if (Array.isArray(args.recipient_email)) {
    recipientEmail = (args.recipient_email as unknown[]).map((r) => String(r).trim());
  }
  if (!recipientEmail || !recipientEmail.length) {
    return { text: "参数错误：recipient_email 必须为邮箱地址或地址列表", isError: true };
  }

  const problems: string[] = [];
  if (isPlaceholder(senderEmail)) problems.push("sender_email 是占位值，请填写真实邮箱地址");
  else if (!EMAIL_RE.test(senderEmail)) problems.push("sender_email 格式不正确");
  if (!senderPassword || isPlaceholder(senderPassword)) {
    problems.push("sender_password 是占位值，请填写 IMAP/SMTP 授权码");
  }
  for (const r of recipientEmail) {
    if (!EMAIL_RE.test(r)) problems.push(`收件人 ${r} 格式不正确`);
  }
  if (problems.length) {
    return { text: "配置未保存：\n- " + problems.join("\n- "), isError: true };
  }

  const existing = loadFileConfig() || {};
  const config: MailConfig = { ...existing };
  config.email = { sender_email: senderEmail, sender_password: String(senderPassword), recipient_email: recipientEmail };
  config.imap_server = String(args.imap_server || existing.imap_server || "imap.qq.com").trim();
  config.smtp_server = String(args.smtp_server || existing.smtp_server || "smtp.qq.com").trim();
  config.imap_port = parseInt(String(args.imap_port || existing.imap_port || 993), 10);
  config.smtp_port = parseInt(String(args.smtp_port || existing.smtp_port || 465), 10);
  config.analysis = config.analysis || {};
  if (args.mailbox_name) config.analysis.mailbox_name = String(args.mailbox_name).trim();

  saveFileConfig(config);

  return {
    text:
      "邮箱配置已保存到: " + CONFIG_PATH + "\n" +
      "sender_email: " + senderEmail + "\n" +
      "recipient_email: " + recipientEmail.join(", ") + "\n" +
      "IMAP: " + config.imap_server + ":" + config.imap_port + "  SMTP: " +
      config.smtp_server + ":" + config.smtp_port + "\n" +
      "（授权码已保存但不会在此显示）接下来可调用 analyze_12306_mail 运行分析。",
    isError: false,
  };
}

function toolAnalyze(): { text: string; isError: boolean } {
  const missing = missingFields(effectiveConfig());
  if (missing.length) {
    return {
      text:
        "❌ 邮箱尚未配置，无法运行分析（缺少: " + missing.join(", ") + "）。\n" +
        "请在可视化配置界面填写：" + UI_HINT + "。\n" +
        "也可以调用 save_mail_config 工具保存配置（写入 " + CONFIG_PATH + "），然后重试本工具。",
      isError: true,
    };
  }

  const config = effectiveConfig();
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(RUN_CONFIG_PATH, JSON.stringify(config, null, 2), "utf-8");

  // 追加启动标记 + 以追加方式打开日志文件，作为子进程 stdout/stderr 目标
  const logFd = openSync(RUN_LOG_PATH, "a");
  writeFileSync(logFd, "\n===== 分析任务启动 " + timestamp() + " =====\n");

  const child = spawn(process.execPath, [CLI_JS, "--config", RUN_CONFIG_PATH], {
    cwd: BUNDLE_DIR,
    detached: true,
    stdio: ["ignore", logFd, logFd],
    windowsHide: true,
  });
  child.unref();
  closeSync(logFd);

  return {
    text:
      "✅ 分析已在后台启动（进程 PID " + child.pid + "）。\n" +
      "邮件量大时耗时较长，请稍后调用 get_analysis_status 查看进度与最终结果（报告由后台任务自动发送）。\n" +
      "运行日志: " + RUN_LOG_PATH,
    isError: false,
  };
}

function toolGetAnalysisStatus(): { text: string; isError: boolean } {
  if (!existsSync(RUN_LOG_PATH)) {
    return {
      text: JSON.stringify({ state: "无运行记录", hint: "先调用 analyze_12306_mail 启动一次分析" }, null, 2),
      isError: false,
    };
  }
  let content = "";
  try {
    content = readFileSync(RUN_LOG_PATH, "utf-8");
  } catch {
    content = "";
  }
  const marker = TERMINAL_MARKERS.find((m) => content.includes(m));
  const lines = content.split("\n").map((l) => l.trim()).filter(Boolean);
  const tail = lines.slice(-40).join("\n") || "(日志为空)";
  let state: string;
  if (marker === "所有任务完成") state = "已完成，报告已发送到收件邮箱";
  else if (marker) state = "已结束：" + marker;
  else state = "运行中";
  return { text: JSON.stringify({ state, log_tail: tail }, null, 2), isError: false };
}

function timestamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function callTool(name: string, args: Record<string, unknown>): { text: string; isError: boolean } {
  switch (name) {
    case "get_mail_config_status":
      return toolGetStatus();
    case "save_mail_config":
      return toolSaveConfig(args);
    case "analyze_12306_mail":
      return toolAnalyze();
    case "get_analysis_status":
      return toolGetAnalysisStatus();
    default:
      return { text: "未知工具: " + name, isError: true };
  }
}

const server = new Server(SERVER_INFO, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const result = callTool(name, (args || {}) as Record<string, unknown>);
  return {
    content: [{ type: "text", text: result.text }],
    isError: result.isError,
  };
});

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log(`mail-analysis-12306 MCP server started, config file: ${CONFIG_PATH}`);
}

main().catch((e) => {
  log(`MCP server fatal: ${(e as Error).message}`);
  process.exit(1);
});
