/**
 * 解析器对账：Node 版 EmailParser vs Python 版（src/engine/email_parser.py）基准。
 * 对比记录条数与每条记录的关键字段。
 *
 * 用法：node scripts/verify-parser.mjs <emails.json> <records_python.json>
 */
import { readFileSync } from "node:fs";
import { EmailParser } from "../dist/lib/emailParser.js";

const [, , emailsPath, pythonRecordsPath] = process.argv;
if (!emailsPath || !pythonRecordsPath) {
  console.error("用法: node scripts/verify-parser.mjs <emails.json> <records_python.json>");
  process.exit(2);
}

const emails = JSON.parse(readFileSync(emailsPath, "utf-8"));
const pythonRecords = JSON.parse(readFileSync(pythonRecordsPath, "utf-8"));

const parser = new EmailParser();
const nodeRecords = parser.parseEmails(emails);

console.log(`Python: ${pythonRecords.length} 条, Node: ${nodeRecords.length} 条`);

// 记录字段白名单（排除 raw_body 这种长文本，逐字段比）
const FIELDS = [
  "type", "subject", "date", "order_number", "train_number",
  "departure_station", "arrival_station", "departure_datetime",
  "departure_date_partial", "price", "seat_type", "passenger_name",
  "carriage", "seat_number", "refund_fee", "actual_spent_amount",
  "actual_refund_amount", "new_ticket_amount", "original_refund_amount",
  "_has_explicit_refund",
];

const norm = (v) => (v === undefined ? null : v);
const num = (v) => (typeof v === "number" ? v : v == null ? null : parseFloat(v));

function recordKey(r) {
  // 用类型+订单号+乘客+车次+日期 生成稳定键，用于跨版配对
  return JSON.stringify([
    r.type,
    r.order_number ?? "",
    r.passenger_name ?? "",
    r.train_number ?? "",
    r.departure_datetime ?? "",
    r.departure_station ?? "",
  ]);
}

let fieldDiffs = 0;
let matched = 0;

// 两版都按出现顺序，逐条配对（parser 输出顺序一致才可这样）
if (pythonRecords.length !== nodeRecords.length) {
  console.log(`❌ 记录条数不一致`);
  process.exit(1);
}

for (let i = 0; i < nodeRecords.length; i++) {
  const n = nodeRecords[i];
  const p = pythonRecords[i];
  const nk = recordKey(n);
  const pk = recordKey(p);
  if (nk !== pk) {
    console.log(`⚠️  第 ${i} 条记录键不匹配：`);
    console.log(`    py: ${pk}`);
    console.log(`    js: ${nk}`);
    continue;
  }
  matched++;
  for (const f of FIELDS) {
    const a = norm(n[f]);
    const b = norm(p[f]);
    if (f === "price" || f === "refund_fee" || f === "actual_spent_amount" ||
        f === "actual_refund_amount" || f === "new_ticket_amount" ||
        f === "original_refund_amount") {
      const na = num(a);
      const nb = num(b);
      if (na === null && nb === null) continue;
      if (na === null || nb === null || Math.abs(na - nb) > 1e-9) {
        fieldDiffs++;
        console.log(`  [${i}] ${f}: py=${JSON.stringify(b)} js=${JSON.stringify(a)}`);
      }
      continue;
    }
    if (JSON.stringify(a) !== JSON.stringify(b)) {
      fieldDiffs++;
      console.log(`  [${i}] ${f}: py=${JSON.stringify(b)} js=${JSON.stringify(a)}`);
    }
  }
}

console.log(`匹配记录 ${matched}/${nodeRecords.length}, 字段差异 ${fieldDiffs} 处`);
process.exit(fieldDiffs === 0 ? 0 : 1);
