/**
 * HTML 报告生成模块 —— 生成可视化统计报告。
 * 逐字移植自 src/engine/html_report.py：结构、CSS、表头、金额格式一一对应。
 */

import { pyRound } from "./round.js";

const TABLE_HEADER_STYLE =
  "background-color:#eaf2ff;" +
  "background:#eaf2ff;" +
  "color:#0f172a;" +
  "-webkit-text-fill-color:#0f172a;";

const FOOTER_STYLE =
  "text-align:center;" +
  "padding:14px 12px 16px;" +
  "color:#64748b;" +
  "-webkit-text-fill-color:#64748b;" +
  "border-top:1px solid #e2ebfb;" +
  "font-size:13px;" +
  "background-color:#f7faff;" +
  "background:#f7faff;";

type AnyObj = Record<string, any>;

export class HTMLReportGenerator {
  _headerCell(label: string, width?: string): string {
    const widthStyle = width ? `width:${width};` : "";
    return `<th bgcolor="#eaf2ff" style="${widthStyle}${TABLE_HEADER_STYLE}">${label}</th>`;
  }

  _formatSafeDate(value: string): string {
    if (!value) return "";
    const safeValue = value.replace(/-/g, "&#8209;").replace(/:/g, "&#8202;:&thinsp;");
    return `<span class="date-text">${safeValue}</span>`;
  }

  _formatAmount(value: unknown): string {
    const n = typeof value === "number" ? value : parseFloat(String(value));
    if (Number.isNaN(n)) return String(value);
    const amount = pyRound(n, 1);
    if (Number.isInteger(amount)) return String(amount);
    return amount.toFixed(1);
  }

  generate(reportData: AnyObj): string {
    try {
      return this._buildHtml(reportData);
    } catch (e) {
      return `<h1>报告生成失败: ${(e as Error).message}</h1>`;
    }
  }

  _buildHtml(report: AnyObj): string {
    const now = new Date();
    const p = (n: number) => String(n).padStart(2, "0");
    const generateTime = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())} ${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`;

    return [
      this._getHtmlHeader(),
      this._getBodyStart(report.filter_info || {}, report.overview || {}),
      this._renderSections(report),
      this._getFooter(generateTime),
      "</div></body></html>",
    ].join("");
  }

  _renderSections(report: AnyObj): string {
    return [
      this._getOverviewSection(report.overview || {}),
      this._getYearlySection(report.yearly_stats || []),
      this._getCitiesSection(report.popular_cities || {}),
      this._getTrainsSection(report.popular_trains || []),
      this._getSeatSection(report.seat_type_stats || []),
      this._getDepartureTimeRankingSection(report.departure_time_ranking || []),
      this._getPassengerSection(report.passenger_stats || []),
    ].join("");
  }

  _getHtmlHeader(): string {
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="format-detection" content="telephone=no,email=no,address=no,url=no">
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light">
    <title>12306出行统计报告</title>
    <style>
        ${this._getCss()}
    </style>
</head>
<body>
    <div class="container">`;
  }

  _getBodyStart(filterInfo: AnyObj, overview: AnyObj): string {
    const filterParts: string[] = [];
    if (filterInfo && (filterInfo.start_year || filterInfo.end_year)) {
      const start = filterInfo.start_year || "";
      const end = filterInfo.end_year || "";
      let rangeText: string;
      if (start && end) rangeText = `${start}年 - ${end}年`;
      else if (start) rangeText = `${start}年起`;
      else rangeText = `截至${end}年`;
      filterParts.push(`<span class="header-meta-item">统计范围: ${rangeText}</span>`);
    }

    const dateRange = overview.date_range || {};
    if (dateRange.start) {
      const start = String(dateRange.start).slice(0, 10);
      const end = String(dateRange.end).slice(0, 10);
      filterParts.push(
        `<span class="header-meta-item">数据时间: <span class="header-date">${this._formatSafeDate(start)} 至 ${this._formatSafeDate(end)}</span></span>`
      );
    }

    const filterHtml = filterParts.length ? `<div class="header-meta">${filterParts.join("")}</div>` : "";

    return `
        <div class="header">
            <h1>12306 出行统计报告</h1>
            <p>基于邮件记录的铁路出行画像</p>
            ${filterHtml}
        </div>
        <div class="content">`;
  }

  _getCss(): string {
    return `
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: #eef5ff;
            padding: 6px;
            line-height: 1.6;
            color: #1f2937;
            color-scheme: light only;
        }
        .container {
            max-width: 1180px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            border: 1px solid #cfe0ff;
            box-shadow: none;
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #1c64f2 0%, #2f80ed 60%, #4f9cf9 100%);
            color: #fff;
            padding: 14px 10px 10px;
            text-align: center;
            -webkit-text-fill-color: #ffffff;
        }
        .header h1 { font-size: 26px !important; line-height: 1.2; margin-bottom: 2px; letter-spacing: 0; font-weight: 700; color: #ffffff !important; -webkit-text-fill-color: #ffffff; }
        .header p { font-size: 15px !important; line-height: 1.35; opacity: 0.96; color: #ffffff !important; -webkit-text-fill-color: #ffffff; }
        .header-meta {
            margin-top: 6px;
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 6px 16px;
        }
        .header-meta-item {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 13px;
            font-weight: 500;
            opacity: 0.98;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff;
        }
        .header-date {
            color: #fff3a3;
            font-weight: 600;
            -webkit-text-fill-color: #fff3a3;
        }
        .content { padding: 14px 14px 12px; }
        .section { margin-bottom: 14px; }
        .section-title {
            font-size: 20px !important;
            line-height: 1.25;
            color: #0f172a;
            margin-bottom: 10px;
            padding-bottom: 6px;
            border-bottom: 1px solid #dbe5f0;
            font-weight: 700;
        }
        .overview-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 4px;
        }
        .stat-card {
            background: #f7faff;
            color: #0f172a;
            padding: 12px 4px 10px;
            border-radius: 10px;
            border: 1px solid #d4e4ff;
            text-align: center;
        }
        .stat-card h3 { font-size: 15px !important; line-height: 1.3; color: #4b5b76; margin-bottom: 6px; font-weight: 700; text-align: center; }
        .stat-card .value { font-size: 22px !important; line-height: 1.2; font-weight: 500; color: #334155 !important; -webkit-text-fill-color: #334155; text-align: center; }
        .date-text {
            color: inherit !important;
            text-decoration: none !important;
            white-space: nowrap;
            pointer-events: none;
        }
        .table-card {
            border: 1px solid #d8e5fb;
            border-radius: 10px;
            overflow: hidden;
            background: #fff;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 0;
            background: white;
            font-size: 15px;
            table-layout: fixed;
        }
        thead {
            background: #eaf2ff;
            color: #0f172a;
        }
        th { padding: 10px 8px; text-align: center; font-weight: 700; word-break: keep-all; font-size: 15px !important; }
        td { padding: 9px 8px; border-bottom: 1px solid #eef2f7; word-break: break-word; text-align: center; font-size: 15px !important; }
        .compact-table th, .compact-table td { white-space: nowrap; }
        .label-cell { text-align: center; }
        .route-cell { white-space: nowrap; }
        .amount-cell { text-align: right !important; }
        tbody tr:nth-child(even) { background-color: #fbfdff; }
        tbody tr:last-child td { border-bottom: none; }
        .highlight {
            color: #d14343 !important;
            -webkit-text-fill-color: #d14343;
            font-weight: 500;
        }
        .footer {
            text-align: center;
            padding: 14px 12px 16px;
            color: #64748b;
            border-top: 1px solid #e2ebfb;
            font-size: 13px;
            background: #f7faff;
        }
        h3.subsection-title {
            margin: 12px 0 7px;
            color: #334155;
            font-size: 16px !important;
            font-weight: 700;
            line-height: 1.25;
        }
        a[x-apple-data-detectors], .date-text a {
            color: inherit !important;
            text-decoration: none !important;
            pointer-events: none !important;
        }
        [data-ogsc] .header,
        [data-ogsc] .header h1,
        [data-ogsc] .header p,
        [data-ogsc] .header-meta-item,
        [data-ogsc] .header-date {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        [data-ogsc] .header-date {
            color: #fff3a3 !important;
            -webkit-text-fill-color: #fff3a3 !important;
        }
        [data-ogsc] .highlight {
            color: #d14343 !important;
            -webkit-text-fill-color: #d14343 !important;
        }
        [data-ogsc] .stat-card .value {
            color: #334155 !important;
            -webkit-text-fill-color: #334155 !important;
        }
        @media (min-width: 1024px) {
            .content { padding: 18px 20px 16px; }
        }
        @media (max-width: 768px) {
            body { padding: 0; }
            .container { border-radius: 10px; }
            .header { padding: 14px 8px 10px; }
            .header h1 { font-size: 21px !important; }
            .header p { font-size: 14px; }
            .header-meta { gap: 4px 10px; }
            .content { padding: 8px 6px 8px; }
            .overview-grid { grid-template-columns: repeat(3, 1fr); }
            table { font-size: 14px; }
            th, td { padding: 8px 8px; font-size: 14px; }
        }
        `;
  }

  _getOverviewSection(overview: AnyObj): string {
    if (!overview || !Object.keys(overview).length) return "";
    return `
            <div class="section">
                <h2 class="section-title">📌 总体概览</h2>
                <div class="overview-grid">
                    <div class="stat-card">
                        <h3>出行次数</h3>
                        <div class="value">${overview.purchase_count ?? 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>退票记录</h3>
                        <div class="value">${overview.refund_count ?? 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>改签记录</h3>
                        <div class="value">${overview.change_count ?? 0}</div>
                    </div>
                    <div class="stat-card">
                        <h3>消费总额</h3>
                        <div class="value">¥${this._formatAmount(overview.net_spent ?? 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>退改扣费</h3>
                        <div class="value">¥${this._formatAmount(overview.refund_change_fee ?? 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>平均票价</h3>
                        <div class="value">¥${this._formatAmount(overview.avg_ticket_price ?? 0)}</div>
                    </div>
                </div>
            </div>
        `;
  }

  _getYearlySection(yearlyStats: AnyObj[]): string {
    if (!yearlyStats.length) return "";
    const sorted = [...yearlyStats].sort((a, b) => b.year - a.year);
    const rows = sorted.map(
      (stat) => `
                <tr>
                    <td>${stat.year}</td>
                    <td>${stat.total_trips}</td>
                    <td class="highlight">¥${this._formatAmount(stat.net_spent)}</td>
                    <td>¥${this._formatAmount(stat.avg_price ?? 0)}</td>
                </tr>
            `
    );
    return `
            <div class="section">
                <h2 class="section-title">📅 年度统计</h2>
                <div class="table-card"><table class="compact-table">
                    <thead>
                        <tr>
                            ${this._headerCell("年份")}
                            ${this._headerCell("出行次数")}
                            ${this._headerCell("消费总额")}
                            ${this._headerCell("平均票价")}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.join("")}
                    </tbody>
                </table></div>
            </div>
        `;
  }

  _getCitiesSection(popularCities: AnyObj): string {
    if (!popularCities || !Object.keys(popularCities).length) return "";
    const parts = ['<div class="section"><h2 class="section-title">🏙️ 城市路线</h2>'];

    if (popularCities.departures?.length) {
      const rows = popularCities.departures.slice(0, 10).map(
        (city: AnyObj, i: number) =>
          `<tr><td>${i + 1}</td><td class="label-cell">${city.city}</td><td>${city.count}</td>` +
          `<td class="highlight">¥${this._formatAmount(city.total_spent ?? 0)}</td></tr>`
      );
      parts.push(`
                <h3 class="subsection-title">出发城市</h3>
                <div class="table-card"><table>
                    <thead><tr>${this._headerCell("排名")}${this._headerCell("城市")}${this._headerCell("出发次数")}${this._headerCell("消费总额")}</tr></thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            `);
    }

    if (popularCities.arrivals?.length) {
      const rows = popularCities.arrivals.slice(0, 10).map(
        (city: AnyObj, i: number) =>
          `<tr><td>${i + 1}</td><td class="label-cell">${city.city}</td><td>${city.count}</td>` +
          `<td class="highlight">¥${this._formatAmount(city.total_spent ?? 0)}</td></tr>`
      );
      parts.push(`
                <h3 class="subsection-title">到达城市</h3>
                <div class="table-card"><table>
                    <thead><tr>${this._headerCell("排名")}${this._headerCell("城市")}${this._headerCell("到达次数")}${this._headerCell("消费总额")}</tr></thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            `);
    }

    if (popularCities.routes?.length) {
      const rows = popularCities.routes.map(
        (route: AnyObj, i: number) =>
          `<tr><td>${i + 1}</td><td class="label-cell route-cell">${route.route}</td><td>${route.count}</td>` +
          `<td class="highlight">¥${this._formatAmount(route.total_spent ?? 0)}</td></tr>`
      );
      parts.push(`
                <h3 class="subsection-title">热门路线</h3>
                <div class="table-card"><table>
                    <thead><tr>${this._headerCell("排名", "52px")}${this._headerCell("路线", "46%")}${this._headerCell("次数", "56px")}${this._headerCell("消费总额", "88px")}</tr></thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            `);
    }

    parts.push("</div>");
    return parts.join("");
  }

  _getTrainsSection(popularTrains: AnyObj[]): string {
    if (!popularTrains.length) return "";
    const rows = popularTrains.map(
      (train: AnyObj, i: number) => `
                <tr>
                    <td>${i + 1}</td>
                    <td class="label-cell">${train.train_number}</td>
                    <td>${train.count}</td>
                    <td class="highlight">¥${this._formatAmount(train.total_spent)}</td>
                </tr>
            `
    );
    return `
            <div class="section">
                <h2 class="section-title">🚄 常坐列车</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>${this._headerCell("排名")}${this._headerCell("车次")}${this._headerCell("乘坐次数")}${this._headerCell("消费总额")}</tr>
                    </thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            </div>
        `;
  }

  _getSeatSection(seatTypeStats: AnyObj[]): string {
    if (!seatTypeStats.length) return "";
    const rows = seatTypeStats.map(
      (seat: AnyObj, i: number) => `
                <tr>
                    <td>${i + 1}</td>
                    <td class="label-cell">${seat.seat_type}</td>
                    <td>${seat.count}</td>
                    <td class="highlight">¥${this._formatAmount(seat.avg_price)}</td>
                </tr>
            `
    );
    return `
            <div class="section">
                <h2 class="section-title">💺 座位偏好</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>${this._headerCell("排名")}${this._headerCell("座位类型")}${this._headerCell("选择次数")}${this._headerCell("平均票价")}</tr>
                    </thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            </div>
        `;
  }

  _getPassengerSection(passengerStats: AnyObj[]): string {
    if (!passengerStats.length) return "";
    const rows = passengerStats.map(
      (passenger: AnyObj, i: number) => `
                <tr>
                    <td>${i + 1}</td>
                    <td class="label-cell">${passenger.passenger_name}</td>
                    <td>${passenger.trip_count}</td>
                    <td class="highlight">¥${this._formatAmount(passenger.net_spent ?? 0)}</td>
                </tr>
            `
    );
    return `
            <div class="section">
                <h2 class="section-title">🧑 乘客统计</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>${this._headerCell("排名")}${this._headerCell("乘客姓名")}${this._headerCell("出行次数")}${this._headerCell("消费总额")}</tr>
                    </thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            </div>
        `;
  }

  _getFooter(generateTime: string): string {
    return `
        </div>
        <div class="footer" bgcolor="#f7faff" style="${FOOTER_STYLE}">
            <p>报告生成时间: ${this._formatSafeDate(generateTime)}</p>
        </div>`;
  }

  _getDepartureTimeRankingSection(ranking: AnyObj[]): string {
    if (!ranking.length) return "";
    const rows = ranking.map(
      (item: AnyObj, i: number) => {
        const hourRange = String(item.hour_range).replace(/-/g, "&#8209;");
        return `
                <tr>
                    <td>${i + 1}</td>
                    <td class="label-cell"><span class="date-text">${hourRange}</span></td>
                    <td>${item.count}</td>
                </tr>
            `;
      }
    );
    return `
            <div class="section">
                <h2 class="section-title">⏰ 出发时间</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>${this._headerCell("排名")}${this._headerCell("时间段")}${this._headerCell("出发次数")}</tr>
                    </thead>
                    <tbody>${rows.join("")}</tbody>
                </table></div>
            </div>
        `;
  }
}
