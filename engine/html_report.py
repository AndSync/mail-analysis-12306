"""
HTML报告生成模块 - 生成美观的可视化统计报告（纯原生实现）
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HTMLReportGenerator:
    """HTML报告生成器"""

    TABLE_HEADER_STYLE = (
        "background-color:#eaf2ff;"
        "background:#eaf2ff;"
        "color:#0f172a;"
        "-webkit-text-fill-color:#0f172a;"
    )
    FOOTER_STYLE = (
        "text-align:center;"
        "padding:14px 12px 16px;"
        "color:#64748b;"
        "-webkit-text-fill-color:#64748b;"
        "border-top:1px solid #e2ebfb;"
        "font-size:13px;"
        "background-color:#f7faff;"
        "background:#f7faff;"
    )

    def _header_cell(self, label, width=None):
        """生成适合邮件客户端的表头单元格"""
        width_style = f"width:{width};" if width else ""
        return (
            f'<th bgcolor="#eaf2ff" '
            f'style="{width_style}{self.TABLE_HEADER_STYLE}">{label}</th>'
        )

    def _format_safe_date(self, value):
        """格式化日期，尽量避免被手机邮件客户端识别成超链接"""
        if not value:
            return ""

        safe_value = value.replace('-', '&#8209;').replace(':', '&#8202;:&thinsp;')
        return f'<span class="date-text">{safe_value}</span>'

    def _format_amount(self, value):
        """格式化金额：小数部分为0时不显示 .0"""
        try:
            amount = round(float(value), 1)
        except (TypeError, ValueError):
            return value

        if amount.is_integer():
            return str(int(amount))

        return f"{amount:.1f}"
    
    def generate(self, report_data):
        """
        生成HTML报告
        :param report_data: 报告数据字典
        :return: HTML字符串
        """
        try:
            html_content = self._build_html(report_data)
            logger.info("HTML报告生成成功")
            return html_content
        except Exception as e:
            logger.error(f"生成HTML报告失败: {e}")
            return f"<h1>报告生成失败: {e}</h1>"
    
    def _build_html(self, report):
        """构建完整的HTML文档"""
        generate_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html_parts = []
        html_parts.append(self._get_html_header())
        html_parts.append(self._get_body_start(report.get('filter_info', {}), report.get('overview', {})))
        html_parts.append(self._get_overview_section(report.get('overview', {})))
        html_parts.append(self._get_yearly_section(report.get('yearly_stats', [])))
        html_parts.append(self._get_cities_section(report.get('popular_cities', {})))
        html_parts.append(self._get_trains_section(report.get('popular_trains', [])))
        html_parts.append(self._get_seat_section(report.get('seat_type_stats', [])))
        html_parts.append(self._get_departure_time_ranking_section(report.get('departure_time_ranking', [])))
        html_parts.append(self._get_passenger_section(report.get('passenger_stats', [])))
        html_parts.append(self._get_footer(generate_time))
        html_parts.append("</div></body></html>")
        
        return ''.join(html_parts)
    
    def _get_html_header(self):
        """获取HTML头部"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="format-detection" content="telephone=no,email=no,address=no,url=no">
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light">
    <title>12306出行统计报告</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <div class="container">"""
    
    def _get_body_start(self, filter_info, overview):
        """获取页面头部"""
        filter_parts = []
        if filter_info and (filter_info.get('start_year') or filter_info.get('end_year')):
            start = filter_info.get('start_year', '')
            end = filter_info.get('end_year', '')
            if start and end:
                range_text = f"{start}年 - {end}年"
            elif start:
                range_text = f"{start}年起"
            else:
                range_text = f"截至{end}年"
            filter_parts.append(f'<span class="header-meta-item">统计范围: {range_text}</span>')

        date_range = overview.get('date_range', {})
        if date_range.get('start'):
            start = date_range['start'][:10]
            end = date_range['end'][:10]
            filter_parts.append(
                f'<span class="header-meta-item">数据时间: <span class="header-date">{self._format_safe_date(start)} 至 {self._format_safe_date(end)}</span></span>'
            )

        filter_html = ""
        if filter_parts:
            filter_html = f'<div class="header-meta">{"".join(filter_parts)}</div>'
        
        return f"""
        <div class="header">
            <h1>12306 出行统计报告</h1>
            <p>基于邮件记录的铁路出行画像</p>
            {filter_html}
        </div>
        <div class="content">"""
    
    def _get_css(self):
        """获取CSS样式"""
        return """
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
        """
    
    def _get_overview_section(self, overview):
        """生成概览部分HTML"""
        if not overview:
            return ""
        
        return f"""
            <div class="section">
                <h2 class="section-title">📌 总体概览</h2>
                <div class="overview-grid">
                    <div class="stat-card">
                        <h3>购票记录</h3>
                        <div class="value">{overview.get('ticket_purchase_count', overview.get('purchase_count', 0))}</div>
                    </div>
                    <div class="stat-card">
                        <h3>退票记录</h3>
                        <div class="value">{overview.get('refund_count', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>改签记录</h3>
                        <div class="value">{overview.get('change_count', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>总消费</h3>
                        <div class="value">¥{self._format_amount(overview.get('total_spent', 0))}</div>
                    </div>
                    <div class="stat-card">
                        <h3>净消费</h3>
                        <div class="value">¥{self._format_amount(overview.get('net_spent', 0))}</div>
                    </div>
                    <div class="stat-card">
                        <h3>平均票价</h3>
                        <div class="value">¥{self._format_amount(overview.get('avg_ticket_price', 0))}</div>
                    </div>
                </div>
            </div>
        """
    
    def _get_yearly_section(self, yearly_stats):
        """生成年份统计部分HTML"""
        if not yearly_stats:
            return ""
        
        # 按年份倒序排列（最新的在前）
        yearly_stats_sorted = sorted(yearly_stats, key=lambda x: x['year'], reverse=True)
        
        rows = []
        for stat in yearly_stats_sorted:
            rows.append(f"""
                <tr>
                    <td>{stat['year']}</td>
                    <td>{stat['total_trips']}</td>
                    <td>¥{self._format_amount(stat['total_spent'])}</td>
                    <td>¥{self._format_amount(stat['total_refunded'])}</td>
                    <td class="highlight">¥{self._format_amount(stat['net_spent'])}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">📅 年度统计</h2>
                <div class="table-card"><table class="compact-table">
                    <thead>
                        <tr>
                            {self._header_cell('年份')}
                            {self._header_cell('购票记录')}
                            {self._header_cell('消费金额')}
                            {self._header_cell('退款金额')}
                            {self._header_cell('净消费')}
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table></div>
            </div>
        """
    
    def _get_cities_section(self, popular_cities):
        """生成城市统计部分HTML"""
        if not popular_cities:
            return ""
        
        html_parts = ['<div class="section"><h2 class="section-title">🏙️ 城市路线</h2>']
        
        # 出发城市
        if popular_cities.get('departures'):
            rows = []
            for idx, city in enumerate(popular_cities['departures'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td class=\"label-cell\">{city['city']}</td><td>{city['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 class="subsection-title">出发城市</h3>
                <div class="table-card"><table>
                    <thead><tr>{self._header_cell('排名')}{self._header_cell('城市')}{self._header_cell('出发次数')}</tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table></div>
            """)
        
        # 到达城市
        if popular_cities.get('arrivals'):
            rows = []
            for idx, city in enumerate(popular_cities['arrivals'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td class=\"label-cell\">{city['city']}</td><td>{city['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 class="subsection-title">到达城市</h3>
                <div class="table-card"><table>
                    <thead><tr>{self._header_cell('排名')}{self._header_cell('城市')}{self._header_cell('到达次数')}</tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table></div>
            """)
        
        # 热门路线
        if popular_cities.get('routes'):
            rows = []
            for idx, route in enumerate(popular_cities['routes'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td class=\"label-cell\">{route['route']}</td><td>{route['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 class="subsection-title">热门路线</h3>
                <div class="table-card"><table style="width: 100%;">
                    <thead><tr>{self._header_cell('排名', '52px')}{self._header_cell('路线', '74%')}{self._header_cell('次数', '64px')}</tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table></div>
            """)
        
        html_parts.append('</div>')
        return ''.join(html_parts)
    
    def _get_trains_section(self, popular_trains):
        """生成列车统计部分HTML"""
        if not popular_trains:
            return ""
        
        rows = []
        for idx, train in enumerate(popular_trains[:10], 1):
            rows.append(f"""
                <tr>
                    <td>{idx}</td>
                    <td class="label-cell">{train['train_number']}</td>
                    <td>{train['count']}</td>
                    <td>¥{self._format_amount(train['avg_price'])}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">🚄 常坐列车</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>{self._header_cell('排名')}{self._header_cell('车次')}{self._header_cell('乘坐次数')}{self._header_cell('平均票价')}</tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table></div>
            </div>
        """
    
    def _get_seat_section(self, seat_type_stats):
        """生成座位类型统计部分HTML"""
        if not seat_type_stats:
            return ""
        
        rows = []
        for seat in seat_type_stats:
            rows.append(f"""
                <tr>
                    <td class="label-cell">{seat['seat_type']}</td>
                    <td>{seat['count']}</td>
                    <td>¥{self._format_amount(seat['avg_price'])}</td>
                    <td class="highlight">¥{self._format_amount(seat['total_spent'])}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">💺 座位偏好</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>{self._header_cell('座位类型')}{self._header_cell('选择次数')}{self._header_cell('平均票价')}{self._header_cell('总消费')}</tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table></div>
            </div>
        """
    
    def _get_passenger_section(self, passenger_stats):
        """生成乘客统计部分HTML"""
        if not passenger_stats:
            return ""
        
        rows = []
        for passenger in passenger_stats:
            rows.append(f"""
                <tr>
                    <td class="label-cell">{passenger['passenger_name']}</td>
                    <td>{passenger['trip_count']}</td>
                    <td class="highlight">¥{self._format_amount(passenger['total_spent'])}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">🧑 乘客统计</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>{self._header_cell('乘客姓名')}{self._header_cell('出行次数')}{self._header_cell('总消费')}</tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table></div>
            </div>
        """
    
    def _get_footer(self, generate_time):
        """生成页脚HTML"""
        return f"""
        </div>
        <div class="footer" bgcolor="#f7faff" style="{self.FOOTER_STYLE}">
            <p>报告生成时间: {self._format_safe_date(generate_time)}</p>
        </div>"""
    
    def _get_departure_time_ranking_section(self, ranking):
        """生成出发时间段排行榜HTML"""
        if not ranking:
            return ""
        
        rows = []
        for idx, item in enumerate(ranking, 1):
            # 处理时间段，防止被识别为超链接
            hour_range = item['hour_range'].replace('-', '&#8209;')
            rows.append(f"""
                <tr>
                    <td>{idx}</td>
                    <td class="label-cell"><span class="date-text">{hour_range}</span></td>
                    <td>{item['count']}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">⏰ 出发时间</h2>
                <div class="table-card"><table>
                    <thead>
                        <tr>{self._header_cell('排名')}{self._header_cell('时间段')}{self._header_cell('出发次数')}</tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table></div>
            </div>
        """
