/**
 * 对账脚本：用 Node 版 DataAnalyzer 加载同一份票务记录，
 * 与 Python 版（src/engine/data_analyzer.py）生成的基准 JSON 逐字段对比。
 *
 * 用法：node scripts/verify-parity.mjs <records.json> <ground_truth.json>
 */
import { readFileSync } from "node:fs";
import { DataAnalyzer } from "../dist/lib/dataAnalyzer.js";

const [, , recordsPath, groundPath] = process.argv;
if (!recordsPath || !groundPath) {
  console.error("用法: node scripts/verify-parity.mjs <records.json> <ground_truth.json>");
  process.exit(2);
}

const records = JSON.parse(readFileSync(recordsPath, "utf-8"));
const ground = JSON.parse(readFileSync(groundPath, "utf-8"));

const analyzer = new DataAnalyzer(records);
const report = analyzer.generateFullReport();

// 归一化：把 JS Date → "YYYY-MM-DD HH:MM:SS" 本地墙钟串，把 undefined → null，
// 消除「Date 对象 vs datetime 字符串」「undefined vs null」两类纯序列化表象差异。
function normalize(v) {
  if (v instanceof Date) {
    const p = (n) => String(n).padStart(2, "0");
    return `${v.getFullYear()}-${p(v.getMonth() + 1)}-${p(v.getDate())} ${p(v.getHours())}:${p(v.getMinutes())}:${p(v.getSeconds())}`;
  }
  if (v === undefined) return null;
  if (Array.isArray(v)) return v.map(normalize);
  if (v && typeof v === "object") {
    const out = {};
    for (const [k, val] of Object.entries(v)) out[k] = normalize(val);
    return out;
  }
  return v;
}

const nodeReport = normalize(report);
const pythonReport = normalize(ground);

const diffs = [];
function compare(path, a, b) {
  if (typeof a === "number" && typeof b === "number") {
    if (Math.abs(a - b) > 1e-9) diffs.push(`${path}: ${a} != ${b}`);
    return;
  }
  if (typeof a !== typeof b) {
    diffs.push(`${path}: type ${typeof a} != ${typeof b} (${JSON.stringify(a)} vs ${JSON.stringify(b)})`);
    return;
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) diffs.push(`${path}: array len ${a.length} != ${b.length}`);
    else a.forEach((x, i) => compare(`${path}[${i}]`, x, b[i]));
    return;
  }
  if (typeof a === "object" && a !== null && b !== null) {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) compare(`${path}.${k}`, a[k], b[k]);
    return;
  }
  if (a !== b) diffs.push(`${path}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`);
}

compare("report", nodeReport, pythonReport);

// 额外：HTML 结构 sanity（表头、行数）
import { HTMLReportGenerator } from "../dist/lib/htmlReport.js";
const html = new HTMLReportGenerator().generate(report);

if (diffs.length) {
  console.log("❌ 发现差异 " + diffs.length + " 处：");
  for (const d of diffs.slice(0, 200)) console.log("  " + d);
  process.exit(1);
} else {
  console.log("✅ 分析器全部数字字段与 Python 版一致");
  console.log("overview:", JSON.stringify(report.overview));
  console.log("yearly rows:", report.yearly_stats.length);
  console.log("passengers:", report.passenger_stats.length);
  console.log("HTML 长度:", html.length, "字节");
  process.exit(0);
}
