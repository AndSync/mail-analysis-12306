/**
 * 邮件解析模块 —— 从 12306 邮件中提取购票/退票/改签信息。
 * 逐条移植自 src/engine/email_parser.py，正则与逻辑一一对应。
 */

export interface EmailData {
  subject: string;
  from: string;
  date: string;
  body: string;
}

export interface TicketRecord {
  type: string;
  subject: string;
  date: string | null;
  raw_body: string;
  [key: string]: unknown;
}

const SEAT_ALIASES: Array<[string, string]> = [
  ["商务座", "商务座"],
  ["特等座", "特等座"],
  ["一等卧", "高级软卧"],
  ["高级软卧", "高级软卧"],
  ["软卧", "软卧"],
  ["硬卧", "硬卧"],
  ["动卧", "动卧"],
  ["一等座", "一等座"],
  ["二等座", "二等座"],
  ["二等包座", "二等座"],
  ["软座", "软座"],
  ["硬座", "硬座"],
  ["无座", "无座"],
];

// Python 版 self.patterns 中的正则在 _extract_with_regex 里仅用到
// departure_station / arrival_station / price / passenger_name 四者，
// 其余为死代码。此处照原样保留完整定义以备对齐。
const PATTERNS: Record<string, RegExp> = {
  order_number: /订单号[:：]\s*([A-Z0-9]+)/,
  train_number: /([GDCKZT]\d+)\w*次/,
  departure_station: /出发[:：]?\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)/,
  arrival_station: /到达[:：]?\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)/,
  departure_time: /(\d{4}年\d{1,2}月\d{1,2}日)\s*[\u4e00-\u9fa5]*\s*(\d{2}:\d{2})/,
  price: /¥\s*(\d+\.?\d*)/,
  seat_type: /([\u4e00-\u9fa5]+座|硬卧|软卧|硬座|软座|商务座|特等座|一等座|二等座)/,
  passenger_name: /乘车人[:：]\s*([\u4e00-\u9fa5·]{2,4})/,
  ticket_status: /(已支付|已退票|已改签|出票成功|订票成功|退票成功|改签成功)/,
};

function toFloat(value: string | null | undefined): number | null {
  if (value == null) return null;
  const n = parseFloat(value);
  return Number.isNaN(n) ? null : n;
}

/** Python re.findall（单捕获组）→ 取全部匹配的组值列表 */
function findAll(pattern: RegExp, text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g"))) {
    if (m[1] != null) out.push(m[1]);
  }
  return out;
}

/** Python re.findall（双捕获组）→ 二元组列表 */
function findAllPairs(pattern: RegExp, text: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const m of text.matchAll(new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g"))) {
    if (m[1] != null && m[2] != null) out.push([m[1], m[2]]);
  }
  return out;
}

/** Python re.search → 首个匹配对象（或 null） */
function search(pattern: RegExp, text: string): RegExpMatchArray | null {
  return text.match(pattern);
}

/** Python re.match → 行首锚定匹配 */
function matchAt(pattern: RegExp, text: string): RegExpMatchArray | null {
  return text.match(new RegExp("^" + pattern.source, pattern.flags));
}

/**
 * 格式化邮件日期为 "%Y-%m-%d %H:%M:%S"。
 * Python 用 email.utils.parsedate_to_datetime + strftime，得到邮件头里「写明的墙钟时间」；
 * 12306/QQ 邮件头恒为 +0800，故按 UTC+8 还原墙钟时间即与 Python 一致。
 */
function formatEmailDate(raw: string): string | null {
  if (!raw) return null;
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)) return raw;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  const shifted = new Date(d.getTime() + 8 * 3600 * 1000);
  return shifted.toISOString().slice(0, 19).replace("T", " ");
}

export class EmailParser {
  seatAliases = SEAT_ALIASES;
  patterns = PATTERNS;

  _toFloat(value: string | null | undefined): number | null {
    return toFloat(value);
  }

  /** 提取实际资金流字段（与 Python _extract_financial_fields 一致） */
  _extractFinancialFields(text: string, ticketType: string | null): Record<string, unknown> {
    const info: Record<string, unknown> = {};
    if (!text) return info;

    const lastAmount = (pattern: RegExp): number | null => {
      const matches = findAll(pattern, text);
      if (!matches.length) return null;
      return toFloat(matches[matches.length - 1]);
    };

    const facePrice = lastAmount(/票价\s*([\d.]+)\s*元/);
    const refundFee = lastAmount(/退票费\s*([\d.]+)\s*元/);
    const refundAmount = lastAmount(/(?:应退票款|实退票款)(?:共计)?\s*([\d.]+)\s*元/);
    const originalRefundAmount = lastAmount(/应退原票款共计\s*([\d.]+)\s*元/);
    const newTicketAmount = lastAmount(/新车票票款共计\s*([\d.]+)\s*元/);
    const paidDelta = lastAmount(
      /(?:需补收票款|支付票款|补收票款|支付差额|需支付票款|补票款共计|实收票款共计)\s*([\d.]+)\s*元/
    );
    const equalChange = text.includes("无支付和退款手续");

    if (refundFee !== null) info["refund_fee"] = refundFee;
    if (facePrice !== null) info["price"] = facePrice;

    if (ticketType === "purchase") {
      if (facePrice !== null) info["actual_spent_amount"] = facePrice;
      return info;
    }

    if (ticketType === "refund") {
      if (refundAmount !== null) {
        info["actual_refund_amount"] = refundAmount;
      } else if (facePrice !== null && refundFee !== null) {
        info["actual_refund_amount"] = Math.max(facePrice - refundFee, 0.0);
      }
      return info;
    }

    if (ticketType === "change") {
      if (newTicketAmount !== null) info["new_ticket_amount"] = newTicketAmount;
      if (originalRefundAmount !== null) info["original_refund_amount"] = originalRefundAmount;

      if (equalChange) {
        info["actual_spent_amount"] = 0.0;
        info["actual_refund_amount"] = 0.0;
        return info;
      }

      if (paidDelta !== null) {
        info["actual_spent_amount"] = paidDelta;
      } else if (newTicketAmount !== null && originalRefundAmount !== null) {
        info["actual_spent_amount"] = Math.max(newTicketAmount - originalRefundAmount, 0.0);
      }

      if (refundAmount !== null) {
        info["actual_refund_amount"] = refundAmount;
        info["_has_explicit_refund"] = true;
      } else if (originalRefundAmount !== null && newTicketAmount !== null) {
        const refundDelta = originalRefundAmount - newTicketAmount;
        if (refundDelta > 0) info["actual_refund_amount"] = refundDelta;
      } else if (originalRefundAmount !== null && paidDelta !== null) {
        info["actual_refund_amount"] = originalRefundAmount;
      }

      if (
        !("actual_spent_amount" in info) &&
        !("actual_refund_amount" in info) &&
        refundAmount !== null &&
        newTicketAmount === null
      ) {
        info["actual_refund_amount"] = refundAmount;
      }
    }

    return info;
  }

  _normalizeSeatType(seatType: string | null | undefined): string | null {
    if (!seatType) return null;

    let value = seatType.replace(/\s+/g, "");
    value = value.replace(/新空调/g, "").replace(/空调/g, "");
    value = value.replace(/新空/g, "");
    value = value.replace(/座票/g, "座").replace(/卧铺票/g, "卧");
    value = value.replace(/二等包/g, "二等");

    if (["上铺", "中铺", "下铺"].some((flag) => value.includes(flag))) {
      if (value.includes("硬")) return "硬卧";
      if (value.includes("软") || value.includes("高级")) return "软卧";
      if (value.includes("动")) return "动卧";
      if (value.includes("卧铺")) return null;
    }

    for (const [raw, normalized] of this.seatAliases) {
      if (value.includes(raw)) return normalized;
    }

    if (value.includes("卧")) {
      if (value.includes("高级")) return "高级软卧";
      if (value.includes("软")) return "软卧";
      if (value.includes("硬")) return "硬卧";
      if (value.includes("动")) return "动卧";
      if (value.includes("卧铺")) return null;
    }

    if (value.includes("座")) {
      if (value.includes("商务")) return "商务座";
      if (value.includes("特等")) return "特等座";
      if (value.includes("一等")) return "一等座";
      if (value.includes("二等")) return "二等座";
      if (value.includes("软")) return "软座";
      if (value.includes("硬")) return "硬座";
    }

    if (value === "无") return "无座";

    return (seatType as string).trim();
  }

  _extractSeatTypeFromText(text: string): string | null {
    if (!text) return null;

    const primary = search(
      /(商务座|特等座|高级软卧|一等座|二等座|二等包座|软卧|硬卧|动卧|软座|硬座|无座)/,
      text
    );
    if (primary) return this._normalizeSeatType(primary[1]);

    const berth = search(/([\u4e00-\u9fa5]*?(?:上|中|下)铺)/, text);
    if (berth) {
      let berthValue = berth[1];
      if (berthValue.startsWith("号")) berthValue = berthValue.slice(1);
      if (text.includes("卧铺")) berthValue = "卧铺" + berthValue;
      return this._normalizeSeatType(berthValue);
    }

    if (text.includes("卧铺")) return null;
    return null;
  }

  parseEmails(emailsData: EmailData[]): TicketRecord[] {
    const records: TicketRecord[] = [];
    let failedCount = 0;
    for (let idx = 0; idx < emailsData.length; idx++) {
      const emailData = emailsData[idx];
      try {
        const emailRecords = this.parseSingleEmail(emailData);
        if (emailRecords.length) records.push(...emailRecords);
        else failedCount += 1;
      } catch {
        continue;
      }
    }
    return records;
  }

  parseSingleEmail(emailData: EmailData): TicketRecord[] {
    const subject = emailData.subject || "";
    const body = emailData.body || "";
    const dateStr = emailData.date || "";
    const cleanBody = this._stripHtmlTags(body);
    const commonInfo = this._extractWithRegex(cleanBody);
    Object.assign(commonInfo, this._extractFinancialFields(cleanBody, null));
    // SimpleHTMLParser 在 Python 版因 bug 恒返回空，HTML 表格提取实为死代码，此处直接跳过。

    const ticketType = this._detectTicketType(subject, body);
    if (!ticketType) return [];

    if (ticketType === "purchase" || ticketType === "refund" || ticketType === "change") {
      const financialInfo = this._extractFinancialFields(cleanBody, ticketType);
      Object.assign(commonInfo, financialInfo);

      let allPassengers = this._extractAllPassengers(body, ticketType, cleanBody);
      if (!allPassengers.length) {
        if (Object.keys(commonInfo).length) {
          allPassengers = [commonInfo];
        } else {
          return [];
        }
      }

      const records: TicketRecord[] = [];
      for (const passengerInfo of allPassengers) {
        const record: TicketRecord = {
          type: ticketType,
          subject,
          date: this._parseDate(dateStr),
          raw_body: body.slice(0, 500),
        };
        for (const [k, v] of Object.entries(commonInfo)) {
          if (!(k in record)) record[k] = v;
        }
        Object.assign(record, passengerInfo);

        // 多人/联程邮件修正：每张票的票价即实付。
        if (ticketType === "purchase" && record.price != null) {
          record.actual_spent_amount = parseFloat(String(record.price));
        }

        if (record.seat_type) {
          record.seat_type = this._normalizeSeatType(record.seat_type as string);
        }

        if ("departure_date_partial" in passengerInfo && record.date) {
          this._inferFullDepartureDate(record);
        }

        records.push(record);
      }
      return records;
    }

    return [];
  }

  _inferFullDepartureDate(record: TicketRecord): void {
    try {
      const emailDateStr = record.date;
      if (!emailDateStr) return;

      const emailDate = new Date(emailDateStr as string);
      if (Number.isNaN(emailDate.getTime())) return;
      const emailYear = emailDate.getFullYear();

      const partialDate = record.departure_date_partial as string | undefined;
      if (!partialDate) return;

      const m = matchAt(/(\d{1,2})月(\d{1,2})日\s+(\d{2}:\d{2})/, partialDate);
      if (m) {
        const month = parseInt(m[1], 10);
        const day = parseInt(m[2], 10);
        const timeStr = m[3];
        const fullDate = new Date(emailYear, month - 1, day);
        const y = fullDate.getFullYear();
        const mm = String(fullDate.getMonth() + 1).padStart(2, "0");
        const dd = String(fullDate.getDate()).padStart(2, "0");
        record.departure_datetime = `${y}-${mm}-${dd} ${timeStr}`;
        delete record.departure_date_partial;
      }
    } catch {
      return;
    }
  }

  _detectTicketType(subject: string, body: string): string | null {
    const text = `${subject} ${body}`;

    if (subject.includes("退票") || subject.includes("退款")) return "refund";
    if (subject.includes("改签") || subject.includes("变更")) return "change";
    if (subject.includes("候补") && subject.includes("退单")) return null;
    if (subject.includes("候补") && (subject.includes("兑现") || subject.includes("成功"))) return "purchase";
    if (
      subject.includes("支付") ||
      subject.includes("购票") ||
      subject.includes("订票") ||
      subject.includes("出票")
    )
      return "purchase";

    for (const kw of ["退票成功", "已退票", "退款", "办理退票", "退票申请"]) {
      if (text.includes(kw)) return "refund";
    }
    for (const kw of ["改签成功", "已改签", "变更到站", "办理改签", "改签申请"]) {
      if (text.includes(kw)) return "change";
    }
    for (const kw of ["购票成功", "订票成功", "出票成功", "已支付", "购买", "预订", "兑现成功", "购票信息"]) {
      if (text.includes(kw)) return "purchase";
    }

    return null;
  }

  _extractAllPassengers(
    body: string,
    ticketType = "purchase",
    cleanBody?: string
  ): Array<Record<string, unknown>> {
    const passengers: Array<Record<string, unknown>> = [];
    const cb = cleanBody ?? this._stripHtmlTags(body);

    const orderMatch = search(/订单号[码:]?\s*([A-Z]\d+)/, cb);
    const orderNumber = orderMatch ? orderMatch[1] : null;

    // 逐行提取（数字序号开头，如 "1.张三,"）
    for (const rawLine of cb.split("\n")) {
      const line = rawLine.trim();
      const m = matchAt(/(\d+)\.([\u4e00-\u9fa5·]{2,4})[,，]/, line);
      if (m) {
        const passengerInfo = this._extractSinglePassengerInfo(line);
        if (Object.keys(passengerInfo).length) {
          if (orderNumber) passengerInfo["order_number"] = orderNumber;
          passengers.push(passengerInfo);
        }
      }
    }

    // 旧版单乘客格式
    if (!passengers.length) {
      const passengerInfo = this._extractWithRegex(cb);
      if (Object.keys(passengerInfo).length && "passenger_name" in passengerInfo) {
        if (orderNumber) passengerInfo["order_number"] = orderNumber;
        passengers.push(passengerInfo);
      }
    }

    // 退票/改签特殊格式（无序号）
    if (!passengers.length && (ticketType === "refund" || ticketType === "change")) {
      const passengerPattern = /([\u4e00-\u9fa5·]{2,4})[,，]\s*((?:\d{4}年)?\d{1,2}月\d{1,2}日\s*\d{2}:\d{2})/g;
      for (const m of cb.matchAll(passengerPattern)) {
        const startPos = m.index!;
        let endPos = cb.indexOf("。", startPos);
        if (endPos === -1) endPos = cb.indexOf("<br", startPos);
        if (endPos === -1) endPos = Math.min(startPos + 200, cb.length);
        const lineContent = cb.slice(startPos, endPos);
        const passengerInfo = this._extractSinglePassengerInfo("1." + lineContent);
        if (Object.keys(passengerInfo).length && "passenger_name" in passengerInfo) {
          if (orderNumber) passengerInfo["order_number"] = orderNumber;
          passengers.push(passengerInfo);
          break;
        }
      }
    }

    return passengers;
  }

  _stripHtmlTags(htmlContent: string): string {
    try {
      let text = htmlContent.replace(/<br\s*\/?>/gi, "\n");
      text = text.replace(/<\/p>/gi, "\n");
      text = text.replace(/<[^>]+>/g, " ");
      text = text.replace(/&nbsp;/g, " ");
      text = text.replace(/&lt;/g, "<");
      text = text.replace(/&gt;/g, ">");
      text = text.replace(/&amp;/g, "&");
      text = text.replace(/&quot;/g, '"');
      text = text.replace(/&#39;/g, "'");
      text = text.replace(/[^\S\n]+/g, " ");
      return text.trim();
    } catch {
      return htmlContent;
    }
  }

  _extractSinglePassengerInfo(line: string): Record<string, unknown> {
    const info: Record<string, unknown> = {};

    const nameMatch = matchAt(/\d+\.([\u4e00-\u9fa5·]{2,4})[,，]/, line);
    if (nameMatch) info["passenger_name"] = nameMatch[1];

    const trainMatch = search(/([GDCKZT]\d+)次(?:列车)?/, line);
    if (trainMatch) info["train_number"] = trainMatch[1];

    const stations = findAllPairs(/([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)\s*[-—→]\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)/, line);
    if (stations.length) {
      info["departure_station"] = stations[0][0];
      info["arrival_station"] = stations[0][1];
    }

    const timeMatch = search(/(\d{4}年)?(\d{1,2}月\d{1,2}日)\s*(\d{2}:\d{2})开?/, line);
    if (timeMatch) {
      const yearPart = timeMatch[1];
      const datePart = timeMatch[2];
      const timePart = timeMatch[3];
      if (yearPart) {
        const fullDate = `${yearPart.replace(/年$/, "")}年${datePart}`;
        const formatted = this._formatChineseDate(fullDate, timePart);
        info["departure_datetime"] = formatted ?? `${fullDate} ${timePart}`;
      } else {
        info["departure_date_partial"] = `${datePart} ${timePart}`;
        info["departure_datetime"] = `${datePart} ${timePart}`;
      }
    }

    const prices = findAll(/票价([\d.]+)元/, line);
    if (prices.length) {
      info["price"] = parseFloat(prices[prices.length - 1]);
    }
    const financialInfo = this._extractFinancialFields(line, null);
    if ("price" in financialInfo) info["price"] = financialInfo["price"];

    const seatType = this._extractSeatTypeFromText(line);
    if (seatType) info["seat_type"] = seatType;

    const carriageMatch = search(/(\d+)车(\d+[A-Z]?)号/, line);
    if (carriageMatch) {
      info["carriage"] = carriageMatch[1];
      info["seat_number"] = carriageMatch[2];
    }

    return info;
  }

  /** 将 "YYYY年M月D日 HH:MM" 解析为 "YYYY-MM-DD HH:MM"（对应 Python strptime %Y年%m月%d日 %H:%M） */
  _formatChineseDate(fullDate: string, timePart: string): string | null {
    const m = matchAt(/(\d{4})年(\d{1,2})月(\d{1,2})日/, fullDate);
    if (!m) return null;
    const y = m[1];
    const mm = m[2].padStart(2, "0");
    const dd = m[3].padStart(2, "0");
    return `${y}-${mm}-${dd} ${timePart}`;
  }

  _extractWithRegex(text: string): Record<string, unknown> {
    const info: Record<string, unknown> = {};

    const orderMatch = search(/订单号[码:]?\s*([A-Z]\d+)/, text);
    if (orderMatch) info["order_number"] = orderMatch[1];

    const trainMatch = search(/([GDCKZT]\d+)次(?:列车)?/, text);
    if (trainMatch) info["train_number"] = trainMatch[1];

    const stations = findAllPairs(/([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)\s*[-—→]\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)/, text);
    if (stations.length) {
      info["departure_station"] = stations[0][0];
      info["arrival_station"] = stations[0][1];
    } else {
      const dep = search(this.patterns.departure_station, text);
      if (dep) info["departure_station"] = dep[1];
      const arr = search(this.patterns.arrival_station, text);
      if (arr) info["arrival_station"] = arr[1];
    }

    const timeMatch = search(/(\d{4}年)?(\d{1,2}月\d{1,2}日)\s*(\d{2}:\d{2})开?/, text);
    if (timeMatch) {
      const yearPart = timeMatch[1];
      const datePart = timeMatch[2];
      const timePart = timeMatch[3];
      if (yearPart) {
        const fullDate = `${yearPart.replace(/年$/, "")}年${datePart}`;
        const formatted = this._formatChineseDate(fullDate, timePart);
        info["departure_datetime"] = formatted ?? `${fullDate} ${timePart}`;
      } else {
        info["departure_date_partial"] = `${datePart} ${timePart}`;
        info["departure_datetime"] = `${datePart} ${timePart}`;
      }
    }

    const prices = findAll(/票价([\d.]+)元/, text);
    if (prices.length) {
      info["price"] = parseFloat(prices[prices.length - 1]);
    } else {
      const yprices = findAll(this.patterns.price, text);
      if (yprices.length) info["price"] = parseFloat(yprices[yprices.length - 1]);
    }

    Object.assign(info, this._extractFinancialFields(text, null));

    const seatType = this._extractSeatTypeFromText(text);
    if (seatType) info["seat_type"] = seatType;

    const nameMatch = search(/\d+\.([\u4e00-\u9fa5·]{2,4})[,，]/, text);
    if (nameMatch) {
      info["passenger_name"] = nameMatch[1];
    } else {
      const pn = search(this.patterns.passenger_name, text);
      if (pn) info["passenger_name"] = pn[1];
    }

    const carriageMatch = search(/(\d+)车(\d+[A-Z]?)号/, text);
    if (carriageMatch) {
      info["carriage"] = carriageMatch[1];
      info["seat_number"] = carriageMatch[2];
    }

    return info;
  }

  _parseDate(dateStr: string): string | null {
    if (!dateStr) return null;
    const formatted = formatEmailDate(dateStr);
    return formatted ?? dateStr;
  }
}
