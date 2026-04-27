"""
邮件解析模块 - 从12306邮件中提取购票、退票、改签信息（纯原生实现）
"""
import re
from datetime import datetime
from html.parser import HTMLParser
import logging

logger = logging.getLogger(__name__)


class SimpleHTMLParser(HTMLParser):
    """简单的HTML解析器，用于提取表格数据"""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_cell = ""
        self.current_row = []
        self.tables = []
        self.current_table = []
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ['td', 'th'] and self.in_row:
            self.in_cell = True
            self.current_cell = ""
    
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
            if self.current_table:
                self.tables.append(self.current_table)
        elif tag == 'tr' and self.in_row:
            self.in_row = False
            if self.current_row:
                self.current_table.append(self.current_row)
        elif tag in ['td', 'th'] and self.in_cell:
            self.in_cell = False
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data.strip()


class EmailParser:
    """邮件解析器"""
    
    def __init__(self):
        # 定义正则表达式模式
        self.patterns = {
            'order_number': r'订单号[:：]\s*([A-Z0-9]+)',
            'train_number': r'([GDCKZT]\d+)\w*次',
            'departure_station': r'出发[:：]?\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)',
            'arrival_station': r'到达[:：]?\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)',
            'departure_time': r'(\d{4}年\d{1,2}月\d{1,2}日)\s*[\u4e00-\u9fa5]*\s*(\d{2}:\d{2})',
            'price': r'¥\s*(\d+\.?\d*)',
            'seat_type': r'([\u4e00-\u9fa5]+座|硬卧|软卧|硬座|软座|商务座|特等座|一等座|二等座)',
            'passenger_name': r'乘车人[:：]\s*([\u4e00-\u9fa5·]{2,4})',
            'ticket_status': r'(已支付|已退票|已改签|出票成功|订票成功|退票成功|改签成功)',
        }
    
    def parse_emails(self, emails_data):
        """
        批量解析邮件
        :param emails_data: 邮件数据列表
        :return: 解析后的票务记录列表
        """
        records = []
        
        for idx, email_data in enumerate(emails_data):
            try:
                record = self.parse_single_email(email_data)
                if record:
                    records.append(record)
                
                if (idx + 1) % 100 == 0:
                    logger.info(f"已解析 {idx + 1}/{len(emails_data)} 封邮件")
                    
            except Exception as e:
                logger.error(f"解析邮件时出错: {e}")
                continue
        
        logger.info(f"成功解析 {len(records)} 条票务记录")
        return records
    
    def parse_single_email(self, email_data):
        """
        解析单封邮件
        :param email_data: 邮件数据字典
        :return: 票务记录字典或None
        """
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        date_str = email_data.get('date', '')
        
        # 判断邮件类型
        ticket_type = self._detect_ticket_type(subject, body)
        
        if not ticket_type:
            return None
        
        # 提取信息
        record = {
            'type': ticket_type,
            'subject': subject,
            'date': self._parse_date(date_str),
            'raw_body': body[:500]  # 保存部分原始内容用于调试
        }
        
        # 根据邮件类型提取具体信息
        if ticket_type in ['purchase', 'refund', 'change']:
            extracted_info = self._extract_ticket_info(body)
            record.update(extracted_info)
        
        return record
    
    def _detect_ticket_type(self, subject, body):
        """
        检测邮件类型
        :return: 'purchase'(购票), 'refund'(退票), 'change'(改签), 或 None
        """
        text = f"{subject} {body}"
        
        # 购票相关关键词
        purchase_keywords = ['购票成功', '订票成功', '出票成功', '已支付', '购买', '预订']
        # 退票相关关键词
        refund_keywords = ['退票成功', '已退票', '退款']
        # 改签相关关键词
        change_keywords = ['改签成功', '已改签', '变更']
        
        for keyword in refund_keywords:
            if keyword in text:
                return 'refund'
        
        for keyword in change_keywords:
            if keyword in text:
                return 'change'
        
        for keyword in purchase_keywords:
            if keyword in text:
                return 'purchase'
        
        return None
    
    def _extract_ticket_info(self, body):
        """
        从邮件正文中提取票务信息
        :param body: 邮件正文
        :return: 提取的信息字典
        """
        info = {}
        
        # 方法1: 使用正则表达式提取
        info.update(self._extract_with_regex(body))
        
        # 方法2: 从HTML表格中提取
        table_info = self._extract_from_html(body)
        info.update(table_info)
        
        return info
    
    def _extract_with_regex(self, text):
        """使用正则表达式提取信息"""
        info = {}
        
        # 提取订单号
        match = re.search(self.patterns['order_number'], text)
        if match:
            info['order_number'] = match.group(1)
        
        # 提取车次
        match = re.search(self.patterns['train_number'], text)
        if match:
            info['train_number'] = match.group(1)
        
        # 提取出发站和到达站
        stations = re.findall(r'([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)\s*[-→]\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)', text)
        if stations:
            info['departure_station'] = stations[0][0]
            info['arrival_station'] = stations[0][1]
        else:
            # 单独提取出发站和到达站
            match = re.search(self.patterns['departure_station'], text)
            if match:
                info['departure_station'] = match.group(1)
            
            match = re.search(self.patterns['arrival_station'], text)
            if match:
                info['arrival_station'] = match.group(1)
        
        # 提取出发时间
        match = re.search(self.patterns['departure_time'], text)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            try:
                departure_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y年%m月%d日 %H:%M")
                info['departure_datetime'] = departure_datetime.strftime("%Y-%m-%d %H:%M")
            except:
                info['departure_datetime'] = f"{date_str} {time_str}"
        
        # 提取价格
        prices = re.findall(self.patterns['price'], text)
        if prices:
            # 取最后一个价格（通常是总价）
            info['price'] = float(prices[-1])
        
        # 提取座位类型
        match = re.search(self.patterns['seat_type'], text)
        if match:
            info['seat_type'] = match.group(1)
        
        # 提取乘客姓名
        match = re.search(self.patterns['passenger_name'], text)
        if match:
            info['passenger_name'] = match.group(1)
        
        return info
    
    def _extract_from_html(self, html_content):
        """从HTML中提取信息"""
        info = {}
        
        try:
            parser = SimpleHTMLParser()
            parser.feed(html_content)
            
            # 遍历所有表格
            for table in parser.tables:
                for row in table:
                    # 合并单元格文本
                    cell_texts = [cell for cell in row if cell]
                    text_combined = ' '.join(cell_texts)
                    
                    # 车次
                    if '车次' in text_combined:
                        for cell in cell_texts:
                            if re.match(r'[GDCKZT]\d+', cell):
                                info['train_number'] = cell
                    
                    # 出发站/到达站
                    if '出发' in text_combined or '始发' in text_combined:
                        for cell in cell_texts:
                            if '站' in cell or cell.endswith(('东', '西', '南', '北')):
                                info['departure_station'] = cell
                    
                    if '到达' in text_combined or '终点' in text_combined:
                        for cell in cell_texts:
                            if '站' in cell or cell.endswith(('东', '西', '南', '北')):
                                info['arrival_station'] = cell
                    
                    # 时间
                    if '时间' in text_combined or '开车' in text_combined:
                        for cell in cell_texts:
                            if re.match(r'\d{4}-\d{2}-\d{2}', cell) or re.match(r'\d{2}:\d{2}', cell):
                                info['departure_datetime'] = cell
                    
                    # 价格
                    if '票价' in text_combined or '金额' in text_combined or '合计' in text_combined:
                        for cell in cell_texts:
                            price_match = re.search(r'¥?\s*(\d+\.?\d*)', cell)
                            if price_match:
                                info['price'] = float(price_match.group(1))
                    
                    # 座位
                    if '席别' in text_combined or '座位' in text_combined or '舱位' in text_combined:
                        for cell in cell_texts:
                            if any(seat in cell for seat in ['座', '卧']):
                                info['seat_type'] = cell
        except Exception as e:
            logger.debug(f"HTML解析失败: {e}")
        
        return info
    
    def _parse_date(self, date_str):
        """
        解析邮件日期
        :param date_str: 日期字符串
        :return: 格式化后的日期字符串
        """
        if not date_str:
            return None
        
        try:
            # 尝试解析标准邮件日期格式
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        
        try:
            # 尝试其他常见格式
            for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    continue
        except:
            pass
        
        return date_str
