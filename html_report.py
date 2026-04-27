"""
HTML报告生成模块 - 生成美观的可视化统计报告（纯原生实现）
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class HTMLReportGenerator:
    """HTML报告生成器"""
    
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
        html_parts.append(self._get_body_start(report.get('filter_info', {})))
        html_parts.append(self._get_overview_section(report.get('overview', {})))
        html_parts.append(self._get_yearly_section(report.get('yearly_stats', [])))
        html_parts.append(self._get_cities_section(report.get('popular_cities', {})))
        html_parts.append(self._get_trains_section(report.get('popular_trains', [])))
        html_parts.append(self._get_seat_section(report.get('seat_type_stats', [])))
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
    <title>12306出行统计报告</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <div class="container">"""
    
    def _get_body_start(self, filter_info):
        """获取页面头部"""
        filter_html = ""
        if filter_info and (filter_info.get('start_year') or filter_info.get('end_year')):
            start = filter_info.get('start_year', '')
            end = filter_info.get('end_year', '')
            if start and end:
                range_text = f"{start}年 - {end}年"
            elif start:
                range_text = f"{start}年起"
            else:
                range_text = f"截至{end}年"
            filter_html = f'<p style="margin-top: 10px; font-size: 0.9em;">统计范围: {range_text}</p>'
        
        return f"""
        <div class="header">
            <h1>🚄 12306出行统计报告</h1>
            <p>您的铁路出行数据分析</p>
            {filter_html}
        </div>
        <div class="content">"""
    
    def _get_css(self):
        """获取CSS样式"""
        return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.1em; opacity: 0.9; }
        .content { padding: 40px; }
        .section { margin-bottom: 40px; }
        .section-title {
            font-size: 1.8em;
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }
        .overview-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-card h3 { font-size: 0.9em; opacity: 0.9; margin-bottom: 10px; }
        .stat-card .value { font-size: 2em; font-weight: bold; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        thead {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        th { padding: 15px; text-align: left; font-weight: 600; }
        td { padding: 12px 15px; border-bottom: 1px solid #eee; }
        tbody tr:hover { background-color: #f8f9ff; }
        tbody tr:last-child td { border-bottom: none; }
        .highlight {
            background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%);
            padding: 2px 8px;
            border-radius: 5px;
            font-weight: bold;
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            border-top: 1px solid #eee;
            font-size: 0.9em;
        }
        @media (max-width: 768px) {
            .header h1 { font-size: 1.8em; }
            .content { padding: 20px; }
            table { font-size: 0.9em; }
        }
        """
    
    def _get_overview_section(self, overview):
        """生成概览部分HTML"""
        if not overview:
            return ""
        
        date_range_html = ""
        if overview.get('date_range', {}).get('start'):
            start = overview['date_range']['start'][:10]
            end = overview['date_range']['end'][:10]
            date_range_html = f'<p style="text-align: center; color: #666; margin-top: 15px;">数据统计时间范围: {start} 至 {end}</p>'
        
        return f"""
            <div class="section">
                <h2 class="section-title">📊 总体概览</h2>
                <div class="overview-grid">
                    <div class="stat-card">
                        <h3>总记录数</h3>
                        <div class="value">{overview.get('total_records', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>购票次数</h3>
                        <div class="value">{overview.get('purchase_count', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>退票次数</h3>
                        <div class="value">{overview.get('refund_count', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>改签次数</h3>
                        <div class="value">{overview.get('change_count', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h3>总消费金额</h3>
                        <div class="value">¥{overview.get('total_spent', 0):.2f}</div>
                    </div>
                    <div class="stat-card">
                        <h3>净消费金额</h3>
                        <div class="value">¥{overview.get('net_spent', 0):.2f}</div>
                    </div>
                </div>
                {date_range_html}
            </div>
        """
    
    def _get_yearly_section(self, yearly_stats):
        """生成年份统计部分HTML"""
        if not yearly_stats:
            return ""
        
        rows = []
        for stat in yearly_stats:
            rows.append(f"""
                <tr>
                    <td><strong>{stat['year']}</strong></td>
                    <td>{stat['total_trips']}</td>
                    <td>{stat['refund_count']}</td>
                    <td>¥{stat['total_spent']:.2f}</td>
                    <td>¥{stat['total_refunded']:.2f}</td>
                    <td class="highlight">¥{stat['net_spent']:.2f}</td>
                    <td>¥{stat['avg_price']:.2f}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">📅 年度统计</h2>
                <table>
                    <thead>
                        <tr>
                            <th>年份</th>
                            <th>出行次数</th>
                            <th>退票次数</th>
                            <th>消费金额</th>
                            <th>退款金额</th>
                            <th>净消费</th>
                            <th>平均票价</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        """
    
    def _get_cities_section(self, popular_cities):
        """生成城市统计部分HTML"""
        if not popular_cities:
            return ""
        
        html_parts = ['<div class="section"><h2 class="section-title">🌆 热门城市</h2>']
        
        # 出发城市
        if popular_cities.get('departures'):
            rows = []
            for idx, city in enumerate(popular_cities['departures'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td><strong>{city['city']}</strong></td><td>{city['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 style="margin: 20px 0 10px 0; color: #667eea;">热门出发城市 TOP 10</h3>
                <table>
                    <thead><tr><th>排名</th><th>城市</th><th>出发次数</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            """)
        
        # 到达城市
        if popular_cities.get('arrivals'):
            rows = []
            for idx, city in enumerate(popular_cities['arrivals'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td><strong>{city['city']}</strong></td><td>{city['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 style="margin: 20px 0 10px 0; color: #667eea;">热门到达城市 TOP 10</h3>
                <table>
                    <thead><tr><th>排名</th><th>城市</th><th>到达次数</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            """)
        
        # 热门路线
        if popular_cities.get('routes'):
            rows = []
            for idx, route in enumerate(popular_cities['routes'][:10], 1):
                rows.append(f"<tr><td>{idx}</td><td><strong>{route['route']}</strong></td><td>{route['count']}</td></tr>")
            
            html_parts.append(f"""
                <h3 style="margin: 20px 0 10px 0; color: #667eea;">热门路线 TOP 10</h3>
                <table>
                    <thead><tr><th>排名</th><th>路线</th><th>次数</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            """)
        
        html_parts.append('</div>')
        return ''.join(html_parts)
    
    def _get_trains_section(self, popular_trains):
        """生成列车统计部分HTML"""
        if not popular_trains:
            return ""
        
        rows = []
        for idx, train in enumerate(popular_trains[:15], 1):
            rows.append(f"""
                <tr>
                    <td>{idx}</td>
                    <td><strong>{train['train_number']}</strong></td>
                    <td>{train['count']}</td>
                    <td>¥{train['avg_price']:.2f}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">🚂 常坐列车 TOP 15</h2>
                <table>
                    <thead>
                        <tr><th>排名</th><th>车次</th><th>乘坐次数</th><th>平均票价</th></tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
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
                    <td><strong>{seat['seat_type']}</strong></td>
                    <td>{seat['count']}</td>
                    <td>¥{seat['avg_price']:.2f}</td>
                    <td class="highlight">¥{seat['total_spent']:.2f}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">💺 座位类型偏好</h2>
                <table>
                    <thead>
                        <tr><th>座位类型</th><th>选择次数</th><th>平均票价</th><th>总消费</th></tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
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
                    <td><strong>{passenger['passenger_name']}</strong></td>
                    <td>{passenger['trip_count']}</td>
                    <td class="highlight">¥{passenger['total_spent']:.2f}</td>
                </tr>
            """)
        
        rows_html = ''.join(rows)
        
        return f"""
            <div class="section">
                <h2 class="section-title">👥 乘客统计</h2>
                <table>
                    <thead>
                        <tr><th>乘客姓名</th><th>出行次数</th><th>总消费</th></tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
        """
    
    def _get_footer(self, generate_time):
        """生成页脚HTML"""
        return f"""
        </div>
        <div class="footer">
            <p>报告生成时间: {generate_time}</p>
            <p style="margin-top: 5px;">© 2026 12306出行统计分析系统</p>
        </div>"""
