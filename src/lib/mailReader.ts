/**
 * 邮件读取模块 —— 连接 IMAP 服务器并获取 12306 邮件。
 * 移植自 src/engine/mail_reader.py；底层用 imapflow（其透明处理 Modified UTF-7 与 MIME 解码）。
 */

import { ImapFlow } from "imapflow";
import { simpleParser } from "mailparser";
import type { EmailData } from "./emailParser.js";
import type { MailConfig } from "./config.js";

const TRUST_MAILBOX_BATCH_SIZE = 40;
const HEADER_BATCH_SIZE = 120;

export class MailReader {
  imapServer: string;
  imapPort: number;
  username: string;
  password: string;
  private client: ImapFlow | null = null;
  private mailboxesCache: string[] | null = null;

  constructor(config: MailConfig) {
    this.imapServer = config.imap_server || "imap.qq.com";
    this.imapPort = config.imap_port || 993;
    this.username = config.email?.sender_email || "";
    this.password = config.email?.sender_password || "";
  }

  async connect(): Promise<boolean> {
    try {
      this.client = new ImapFlow({
        host: this.imapServer,
        port: this.imapPort,
        secure: true,
        auth: { user: this.username, pass: this.password },
        logger: false,
      });
      await this.client.connect();
      return true;
    } catch {
      return false;
    }
  }

  async disconnect(): Promise<void> {
    if (this.client) {
      try {
        await this.client.logout();
      } catch {
        // ignore
      }
      this.client = null;
    }
  }

  _encodeMailboxName(mailboxName: string): string {
    if (!mailboxName) return mailboxName;
    let result = "";
    let buffer: string[] = [];
    const flush = () => {
      if (!buffer.length) return;
      const raw = Buffer.from(buffer.join(""), "utf16le"); // utf-16-be => 交换字节
      const be = Buffer.from(raw).swap16();
      const encoded = be.toString("base64").replace(/=+$/, "").replace(/\//g, ",");
      result += "&" + encoded + "-";
      buffer = [];
    };
    for (const ch of mailboxName) {
      const code = ch.codePointAt(0)!;
      if (code >= 0x20 && code <= 0x7e && ch !== "&") {
        flush();
        result += ch;
      } else if (ch === "&") {
        flush();
        result += "&-";
      } else {
        buffer.push(ch);
      }
    }
    flush();
    return result;
  }

  _decodeMailboxName(mailboxName: string): string {
    if (!mailboxName || !mailboxName.includes("&")) return mailboxName;
    let result = "";
    let i = 0;
    while (i < mailboxName.length) {
      const ch = mailboxName[i];
      if (ch !== "&") {
        result += ch;
        i++;
        continue;
      }
      const end = mailboxName.indexOf("-", i);
      if (end === -1) {
        result += mailboxName.slice(i);
        break;
      }
      const token = mailboxName.slice(i + 1, end);
      if (token === "") {
        result += "&";
      } else {
        const b64 = token.replace(/,/g, "/");
        const padding = "=".repeat((4 - (b64.length % 4)) % 4);
        const buf = Buffer.from(b64 + padding, "base64").swap16();
        result += buf.toString("utf16le");
      }
      i = end + 1;
    }
    return result;
  }

  _getMailboxAliases(mailboxName: string): Set<string> {
    const aliases = new Set<string>([mailboxName]);
    if (mailboxName) {
      aliases.add(this._encodeMailboxName(mailboxName));
      aliases.add(this._decodeMailboxName(mailboxName));
      if (mailboxName.includes("/")) aliases.add(mailboxName.split("/").pop()!);
    }
    return new Set([...aliases].filter(Boolean));
  }

  async listAllMailboxes(): Promise<string[]> {
    if (!this.client) return [];
    try {
      const list = await this.client.list();
      const mailboxList: string[] = [];
      for (const box of list) {
        const name = box.path;
        if (name && !name.startsWith("[Gmail]")) mailboxList.push(name);
      }
      this.mailboxesCache = mailboxList;
      return mailboxList;
    } catch {
      return [];
    }
  }

  /** 解析文件夹名 → 返回 imapflow 可打开的路径（等价于 Python _resolve_mailbox_name）。 */
  async _resolveMailboxName(mailboxName: string): Promise<string> {
    const mailboxes = this.mailboxesCache || (await this.listAllMailboxes());
    this.mailboxesCache = mailboxes;

    const candidates = [...this._getMailboxAliases(mailboxName)];

    for (const candidate of candidates) {
      if (mailboxes.includes(candidate)) return candidate;
    }

    for (const existing of mailboxes) {
      const decodedExisting = this._decodeMailboxName(existing);
      const existingAliases = new Set([...this._getMailboxAliases(decodedExisting), existing]);
      if (candidates.some((c) => existing.endsWith(c))) return existing;
      if ([...existingAliases].some((a) => candidates.includes(a))) return existing;
    }

    // 兜底：用编码名（imapflow 能自行解码，通常直接可用）
    return mailboxName;
  }

  _buildSearchCriteria(startDate?: string | null, endDate?: string | null): {
    since?: Date;
    before?: Date;
  } {
    const criteria: { since?: Date; before?: Date } = {};
    if (startDate) criteria.since = parseImapDate(startDate);
    if (endDate) criteria.before = parseImapDate(endDate);
    return criteria;
  }

  _is12306Email(emailData: { from?: string; subject?: string; body?: string } | null): boolean {
    if (!emailData) return false;
    const fromAddr = (emailData.from || "").toLowerCase();
    const subject = emailData.subject || "";
    const body = emailData.body || "";
    const text = `${subject}\n${body}`.toLowerCase();

    const senderKeywords = ["12306@rails.com.cn", "12306.cn", "中国铁路客户服务中心"];
    const textKeywords = ["12306", "订票", "购票", "出票", "退票", "改签", "候补", "车次", "席别", "订单号"];

    if (senderKeywords.some((k) => fromAddr.includes(k))) return true;
    if (fromAddr.includes("12306")) return true;
    return textKeywords.some((k) => text.includes(k));
  }

  async search12306EmailsInMailbox(
    mailboxName: string,
    startDate?: string | null,
    endDate?: string | null,
    limit?: number | null,
    trustMailbox = false
  ): Promise<EmailData[]> {
    if (!this.client) return [];
    const emailsData: EmailData[] = [];
    try {
      const serverName = await this._resolveMailboxName(mailboxName);
      let mailbox;
      try {
        mailbox = await this.client.mailboxOpen(serverName, { readOnly: true });
      } catch {
        return emailsData;
      }
      const mailCount = mailbox.exists;
      if (mailCount === 0) return emailsData;

      const searchCriteria = this._buildSearchCriteria(startDate, endDate);
      const searchResult = await this.client.search(searchCriteria);
      if (!searchResult || searchResult.length === 0) return emailsData;

      let uids: number[] = searchResult;
      if (limit && uids.length > limit) uids = uids.slice(-limit);

      if (trustMailbox) {
        for (let start = 0; start < uids.length; start += TRUST_MAILBOX_BATCH_SIZE) {
          const batch = uids.slice(start, start + TRUST_MAILBOX_BATCH_SIZE);
          const msgs = await this.client.fetchAll(batch, { source: true }, { uid: true });
          for (const msg of msgs) {
            const emailData = await this._parseRaw(msg.source);
            if (emailData) emailsData.push(emailData);
          }
        }
      } else {
        // 预筛头部，再逐封取正文（仅 scan-all 模式使用）
        const candidateUids: number[] = [];
        for (let start = 0; start < uids.length; start += HEADER_BATCH_SIZE) {
          const batch = uids.slice(start, start + HEADER_BATCH_SIZE);
          const msgs = await this.client.fetchAll(
            batch,
            { uid: true, envelope: true },
            { uid: true }
          );
          for (const msg of msgs) {
            const headerData = {
              from: msg.envelope?.from?.[0]?.address || "",
              subject: msg.envelope?.subject || "",
              body: "",
            };
            if (this._is12306Email(headerData)) candidateUids.push(msg.uid);
          }
        }
        for (const uid of candidateUids) {
          const msgs = await this.client.fetchAll(uid, { source: true }, { uid: true });
          const msg = msgs[0];
          if (!msg) continue;
          const emailData = await this._parseRaw(msg.source);
          if (emailData && this._is12306Email(emailData)) emailsData.push(emailData);
        }
      }

      return emailsData;
    } catch {
      return emailsData;
    }
  }

  async search12306Emails(
    startDate?: string | null,
    endDate?: string | null,
    limit = 10000,
    mailboxName?: string | null
  ): Promise<EmailData[]> {
    const allEmailsData: EmailData[] = [];
    const seenKeys = new Set<string>();

    const extendUnique = (items: EmailData[]) => {
      for (const item of items) {
        const key = JSON.stringify([item.date || "", item.subject || "", item.from || ""]);
        if (seenKeys.has(key)) continue;
        seenKeys.add(key);
        allEmailsData.push(item);
      }
    };

    if (mailboxName) {
      extendUnique(await this.search12306EmailsInMailbox(mailboxName, startDate, endDate, limit, true));
    } else {
      const mailboxes = await this.listAllMailboxes();
      if (!mailboxes.length) return allEmailsData;
      const ordered = ["INBOX", ...mailboxes.filter((b) => b !== "INBOX")];
      for (const mailbox of ordered) {
        const remainingLimit = limit ? limit - allEmailsData.length : null;
        if (remainingLimit !== null && remainingLimit <= 0) break;
        const folderEmails = await this.search12306EmailsInMailbox(
          mailbox,
          startDate,
          endDate,
          remainingLimit,
          false
        );
        extendUnique(folderEmails);
      }
    }
    return allEmailsData;
  }

  private async _parseRaw(source: Buffer | null | undefined): Promise<EmailData | null> {
    if (!source) return null;
    try {
      const parsed = await simpleParser(source);
      const from = parsed.from?.text || "";
      const subject = parsed.subject || "";
      const date = (parsed.headers.get("date") as string) || "";
      const body = (parsed.html as string | false) || (parsed.text as string | false) || "";
      return { subject, from, date, body: body as string };
    } catch {
      return null;
    }
  }
}

/** 解析 Python 的 IMAP 日期串（如 "01-Jan-2020"）为 Date（本地时区，语义与 SINCE/BEFORE 一致）。 */
function parseImapDate(s: string): Date {
  const months: Record<string, number> = {
    Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
    Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11,
  };
  const m = s.match(/^(\d{2})-([A-Za-z]{3})-(\d{4})$/);
  if (m) return new Date(parseInt(m[3], 10), months[m[2]], parseInt(m[1], 10));
  return new Date(s);
}
