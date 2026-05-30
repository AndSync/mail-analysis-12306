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
        self.seat_aliases = [
            ('商务座', '商务座'),
            ('特等座', '特等座'),
            ('一等卧', '高级软卧'),
            ('高级软卧', '高级软卧'),
            ('软卧', '软卧'),
            ('硬卧', '硬卧'),
            ('动卧', '动卧'),
            ('一等座', '一等座'),
            ('二等座', '二等座'),
            ('二等包座', '二等座'),
            ('软座', '软座'),
            ('硬座', '硬座'),
            ('无座', '无座'),
        ]

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

    def _to_float(self, value):
        """安全转换金额"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_financial_fields(self, text, ticket_type):
        """
        提取实际资金流字段
        - purchase: actual_spent_amount
        - refund: actual_refund_amount / refund_fee
        - change: actual_spent_amount / actual_refund_amount / change_fee
        """
        info = {}

        if not text:
            return info

        def last_amount(pattern):
            matches = re.findall(pattern, text)
            if not matches:
                return None
            return self._to_float(matches[-1])

        face_price = last_amount(r'票价\s*([\d.]+)\s*元')
        refund_fee = last_amount(r'退票费\s*([\d.]+)\s*元')
        refund_amount = last_amount(r'(?:应退票款|实退票款)(?:共计)?\s*([\d.]+)\s*元')
        original_refund_amount = last_amount(r'应退原票款共计\s*([\d.]+)\s*元')
        new_ticket_amount = last_amount(r'新车票票款共计\s*([\d.]+)\s*元')
        paid_delta = last_amount(r'(?:需补收票款|支付票款|补收票款|支付差额|需支付票款|补票款共计|实收票款共计)\s*([\d.]+)\s*元')
        equal_change = '无支付和退款手续' in text

        if refund_fee is not None:
            info['refund_fee'] = refund_fee
        if face_price is not None:
            info['price'] = face_price

        if ticket_type == 'purchase':
            if face_price is not None:
                info['actual_spent_amount'] = face_price
            return info

        if ticket_type == 'refund':
            if refund_amount is not None:
                info['actual_refund_amount'] = refund_amount
            elif face_price is not None and refund_fee is not None:
                info['actual_refund_amount'] = max(face_price - refund_fee, 0.0)
            return info

        if ticket_type == 'change':
            if new_ticket_amount is not None:
                info['new_ticket_amount'] = new_ticket_amount
            if original_refund_amount is not None:
                info['original_refund_amount'] = original_refund_amount

            if equal_change:
                info['actual_spent_amount'] = 0.0
                info['actual_refund_amount'] = 0.0
                return info

            if paid_delta is not None:
                info['actual_spent_amount'] = paid_delta
            elif new_ticket_amount is not None and original_refund_amount is not None:
                info['actual_spent_amount'] = max(new_ticket_amount - original_refund_amount, 0.0)

            if refund_amount is not None:
                info['actual_refund_amount'] = refund_amount
            elif original_refund_amount is not None and new_ticket_amount is not None:
                refund_delta = original_refund_amount - new_ticket_amount
                if refund_delta > 0:
                    info['actual_refund_amount'] = refund_delta
            elif original_refund_amount is not None and paid_delta is not None:
                info['actual_refund_amount'] = original_refund_amount

            if (
                'actual_spent_amount' not in info and
                'actual_refund_amount' not in info and
                refund_amount is not None and
                new_ticket_amount is None
            ):
                info['actual_refund_amount'] = refund_amount

        return info

    def _normalize_seat_type(self, seat_type):
        """标准化座位类型"""
        if not seat_type:
            return None

        value = re.sub(r'\s+', '', seat_type)
        value = value.replace('新空调', '').replace('空调', '')
        value = value.replace('新空', '')
        value = value.replace('座票', '座').replace('卧铺票', '卧')
        value = value.replace('二等包', '二等')

        if any(flag in value for flag in ['上铺', '中铺', '下铺']):
            if '硬' in value:
                return '硬卧'
            if '软' in value or '高级' in value:
                return '软卧'
            if '动' in value:
                return '动卧'
            if '卧铺' in value:
                return None

        for raw, normalized in self.seat_aliases:
            if raw in value:
                return normalized

        if '卧' in value:
            if '高级' in value:
                return '高级软卧'
            if '软' in value:
                return '软卧'
            if '硬' in value:
                return '硬卧'
            if '动' in value:
                return '动卧'
            if '卧铺' in value:
                return None

        if '座' in value:
            if '商务' in value:
                return '商务座'
            if '特等' in value:
                return '特等座'
            if '一等' in value:
                return '一等座'
            if '二等' in value:
                return '二等座'
            if '软' in value:
                return '软座'
            if '硬' in value:
                return '硬座'

        if value == '无':
            return '无座'

        return seat_type.strip()

    def _extract_seat_type_from_text(self, text):
        """从文本中优先提取标准席别，再兜底提取铺位描述"""
        if not text:
            return None

        primary_match = re.search(
            r'(商务座|特等座|高级软卧|一等座|二等座|二等包座|软卧|硬卧|动卧|软座|硬座|无座)',
            text
        )
        if primary_match:
            return self._normalize_seat_type(primary_match.group(1))

        berth_match = re.search(r'([\u4e00-\u9fa5]*?(?:上|中|下)铺)', text)
        if berth_match:
            berth_value = berth_match.group(1)
            if berth_value.startswith('号'):
                berth_value = berth_value[1:]
            if '卧铺' in text:
                berth_value = f"卧铺{berth_value}"
            return self._normalize_seat_type(berth_value)

        if '卧铺' in text:
            return None

        return None
    
    def parse_emails(self, emails_data):
        """
        批量解析邮件
        :param emails_data: 邮件数据列表
        :return: 解析后的票务记录列表
        """
        records = []
        failed_count = 0
        
        for idx, email_data in enumerate(emails_data):
            try:
                # parse_single_email 现在返回一个列表（可能包含多个乘客）
                email_records = self.parse_single_email(email_data)
                if email_records:
                    records.extend(email_records)
                else:
                    failed_count += 1
                    # 记录前10个失败邮件的主题，用于调试
                    if failed_count <= 10:
                        subject = email_data.get('subject', '无主题')
                        logger.warning(f"邮件 {idx+1} 解析失败，主题: {subject[:50]}")
                
                if (idx + 1) % 100 == 0:
                    logger.info(f"已解析 {idx + 1}/{len(emails_data)} 封邮件")
                    
            except Exception as e:
                logger.error(f"解析邮件时出错: {e}")
                continue
        
        logger.info(f"成功解析 {len(records)} 条票务记录")
        logger.info(f"未解析邮件数: {failed_count}/{len(emails_data)}")
        return records
    
    def parse_single_email(self, email_data):
        """
        解析单封邮件（可能包含多个乘客）
        :param email_data: 邮件数据字典
        :return: 票务记录列表（多人订单会拆分成多条记录）
        """
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        date_str = email_data.get('date', '')
        clean_body = self._strip_html_tags(body)
        common_info = self._extract_with_regex(clean_body)
        common_info.update(self._extract_financial_fields(clean_body, None))
        if body and '<' in body and '>' in body:
            html_info = self._extract_from_html(body)
            for key, value in html_info.items():
                common_info.setdefault(key, value)
        
        # 判断邮件类型
        ticket_type = self._detect_ticket_type(subject, body)
        
        if not ticket_type:
            return []
        
        # 根据邮件类型提取具体信息
        if ticket_type in ['purchase', 'refund', 'change']:
            financial_info = self._extract_financial_fields(clean_body, ticket_type)
            for key, value in financial_info.items():
                common_info[key] = value
            # 提取所有乘客的信息
            all_passengers = self._extract_all_passengers(body, ticket_type, clean_body=clean_body)
            
            if not all_passengers:
                if common_info:
                    all_passengers = [common_info]
                else:
                    # 如果是退票或改签但没有提取到乘客信息，记录警告
                    if ticket_type in ['refund', 'change']:
                        logger.warning(f"{ticket_type}邮件未提取到乘客信息，主题: {subject[:50]}")
                    return []
            
            # 为每个乘客创建一条记录
            records = []
            for passenger_info in all_passengers:
                record = {
                    'type': ticket_type,
                    'subject': subject,
                    'date': self._parse_date(date_str),
                    'raw_body': body[:500]  # 保存部分原始内容用于调试
                }
                for key, value in common_info.items():
                    record.setdefault(key, value)
                record.update(passenger_info)
                if record.get('seat_type'):
                    record['seat_type'] = self._normalize_seat_type(record['seat_type'])
                
                # 处理旧版邮件的日期（没有年份的情况）
                if 'departure_date_partial' in passenger_info and record.get('date'):
                    record = self._infer_full_departure_date(record)
                
                records.append(record)
            
            return records
        
        return []
    
    def _infer_full_departure_date(self, record):
        """
        根据邮件日期推断完整的出发日期（用于旧版邮件）
        :param record: 票务记录
        :return: 更新后的记录
        """
        try:
            # 邮件发送日期
            email_date_str = record.get('date')  # 格式: "2012-01-24 10:30:00"
            if not email_date_str:
                return record
            
            email_date = datetime.strptime(email_date_str[:10], "%Y-%m-%d")
            email_year = email_date.year
            
            # 部分出发日期（没有年份）
            partial_date = record.get('departure_date_partial')  # 格式: "01月24日 19:28"
            if not partial_date:
                return record
            
            # 提取月和日
            match = re.match(r'(\d{1,2})月(\d{1,2})日\s+(\d{2}:\d{2})', partial_date)
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                time_str = match.group(3)
                
                # 构建完整日期
                full_date = datetime(email_year, month, day)
                
                # 如果出发日期早于邮件日期，说明是下一年（跨年情况）
                # 例如：邮件是2012-01-24，出发日期是01月25日，那么是2012年
                # 但如果出发日期是01月20日，可能是2011年（不太可能，通常是未来）
                if full_date < email_date:
                    # 出发日期在邮件日期之前，可能是下一年
                    # 但12306通常不会卖这么早的票，所以还是用当前年
                    pass
                
                record['departure_datetime'] = full_date.strftime("%Y-%m-%d") + " " + time_str
                # 删除临时字段
                if 'departure_date_partial' in record:
                    del record['departure_date_partial']
        except Exception as e:
            logger.debug(f"推断出发日期失败: {e}")
        
        return record
    
    def _detect_ticket_type(self, subject, body):
        """
        检测邮件类型
        :return: 'purchase'(购票), 'refund'(退票), 'change'(改签), 或 None
        """
        text = f"{subject} {body}"
        
        # 先检查主题（更准确）
        if '退票' in subject or '退款' in subject:
            return 'refund'
        if '改签' in subject or '变更' in subject:
            return 'change'
        if '候补' in subject and ('兑现' in subject or '成功' in subject):
            return 'purchase'  # 候补兑现成功也算购票
        if '支付' in subject or '购票' in subject or '订票' in subject or '出票' in subject:
            return 'purchase'
        
        # 再检查正文关键词
        # 退票相关关键词
        refund_keywords = ['退票成功', '已退票', '退款', '办理退票', '退票申请']
        for keyword in refund_keywords:
            if keyword in text:
                return 'refund'
        
        # 改签相关关键词
        change_keywords = ['改签成功', '已改签', '变更到站', '办理改签', '改签申请']
        for keyword in change_keywords:
            if keyword in text:
                return 'change'
        
        # 购票相关关键词
        purchase_keywords = ['购票成功', '订票成功', '出票成功', '已支付', '购买', '预订', '兑现成功', '购票信息']
        for keyword in purchase_keywords:
            if keyword in text:
                return 'purchase'
        
        return None
    
    def _extract_all_passengers(self, body, ticket_type='purchase', clean_body=None):
        """
        提取邮件中所有乘客的信息（支持单人/多人订单）
        :param body: 邮件正文（可能是HTML）
        :param ticket_type: 邮件类型
        :param clean_body: 已清洗的纯文本，避免重复清洗
        :return: 乘客信息列表，每个元素是一个字典
        """
        passengers = []
        
        if clean_body is None:
            clean_body = self._strip_html_tags(body)
        
        # 提取所有订单号（一封邮件共用一个订单号）
        order_match = re.search(r'订单号[码:]?\s*([A-Z]\d+)', clean_body)
        order_number = order_match.group(1) if order_match else None
        
        # 逐行提取乘客信息
        lines = clean_body.split('\n')
        for line in lines:
            line = line.strip()
            # 匹配以数字序号开头的行，如 "1.张三," 或 "1.张三，"
            match = re.match(r'(\d+)\.([\u4e00-\u9fa5·]{2,4})[,，]', line)
            if match:
                passenger_info = self._extract_single_passenger_info(line)
                if passenger_info:
                    if order_number:
                        passenger_info['order_number'] = order_number
                    passengers.append(passenger_info)
        
        # 如果没有找到多行格式，尝试旧版格式（所有人信息在一行）
        if not passengers:
            # 尝试匹配单个乘客
            passenger_info = self._extract_with_regex(clean_body)
            if passenger_info and 'passenger_name' in passenger_info:
                if order_number:
                    passenger_info['order_number'] = order_number
                passengers.append(passenger_info)
        
        # 如果还是没有找到，尝试匹配退票/改签邮件的特殊格式（没有序号）
        if not passengers and ticket_type in ['refund', 'change']:
            # 匹配类似 "张三，2024年01月15日08:00开，北京西站-上海虹桥站" 或 "李四，02月27日16:54，新乡东—北京西" 的格式
            passenger_pattern = r'([\u4e00-\u9fa5·]{2,4})[,，]\s*((?:\d{4}年)?\d{1,2}月\d{1,2}日\s*\d{2}:\d{2})'
            matches = re.finditer(passenger_pattern, clean_body)
            for match in matches:
                # 从匹配位置开始提取该行信息
                start_pos = match.start()
                # 找到该行的结束位置
                end_pos = clean_body.find('。', start_pos)
                if end_pos == -1:
                    end_pos = clean_body.find('<br', start_pos)
                if end_pos == -1:
                    end_pos = min(start_pos + 200, len(clean_body))
                
                line_content = clean_body[start_pos:end_pos]
                passenger_info = self._extract_single_passenger_info(f"1.{line_content}")
                if passenger_info and 'passenger_name' in passenger_info:
                    if order_number:
                        passenger_info['order_number'] = order_number
                    passengers.append(passenger_info)
                    break  # 只取第一个匹配的乘客
        
        logger.debug(f"从邮件中提取到 {len(passengers)} 个乘客")
        return passengers
    
    def _strip_html_tags(self, html_content):
        """
        清理HTML标签，提取纯文本
        :param html_content: HTML内容
        :return: 纯文本
        """
        try:
            # 将 <br> 和 </p> 转换为换行（在处理标签之前）
            text = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)
            text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
            
            # 移除所有HTML标签
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # 将 HTML 实体转换为普通字符
            text = text.replace('&nbsp;', ' ')
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
            text = text.replace('&amp;', '&')
            text = text.replace('&quot;', '"')
            text = text.replace('&#39;', "'")
            
            # 移除多余的空白字符，但保留换行
            text = re.sub(r'[^\S\n]+', ' ', text)
            
            return text.strip()
        except Exception as e:
            logger.debug(f"HTML清理失败: {e}")
            return html_content
    
    def _extract_single_passenger_info(self, line):
        """
        从单行文本中提取一个乘客的完整信息
        :param line: 包含乘客信息的文本行
        :return: 乘客信息字典
        """
        info = {}
        
        # 提取乘客姓名（格式：1.张三,）
        name_match = re.match(r'\d+\.([\u4e00-\u9fa5·]{2,4})[,，]', line)
        if name_match:
            info['passenger_name'] = name_match.group(1)
        
        # 提取车次
        train_match = re.search(r'([GDCKZT]\d+)次(?:列车)?', line)
        if train_match:
            info['train_number'] = train_match.group(1)
        
        # 提取出发站和到达站
        stations = re.findall(r'([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)\s*[-—→]\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)', line)
        if stations:
            info['departure_station'] = stations[0][0]
            info['arrival_station'] = stations[0][1]
        
        # 提取时间（支持有年份和无年份）
        time_match = re.search(r'(\d{4}年)?(\d{1,2}月\d{1,2}日)\s*(\d{2}:\d{2})开?', line)
        if time_match:
            year_part = time_match.group(1)
            date_part = time_match.group(2)
            time_part = time_match.group(3)
            
            if year_part:
                full_date = f"{year_part.rstrip('年')}年{date_part}"
                try:
                    departure_datetime = datetime.strptime(f"{full_date} {time_part}", "%Y年%m月%d日 %H:%M")
                    info['departure_datetime'] = departure_datetime.strftime("%Y-%m-%d %H:%M")
                except:
                    info['departure_datetime'] = f"{full_date} {time_part}"
            else:
                info['departure_date_partial'] = f"{date_part} {time_part}"
                info['departure_datetime'] = f"{date_part} {time_part}"
        
        # 提取价格
        prices = re.findall(r'票价([\d.]+)元', line)
        if prices:
            info['price'] = float(prices[-1])

        financial_info = self._extract_financial_fields(line, None)
        if 'price' in financial_info:
            info['price'] = financial_info['price']
        
        # 提取座位类型
        seat_type = self._extract_seat_type_from_text(line)
        if seat_type:
            info['seat_type'] = seat_type
        
        # 提取车厢和座位号
        carriage_match = re.search(r'(\d+)车(\d+[A-Z]?)号', line)
        if carriage_match:
            info['carriage'] = carriage_match.group(1)
            info['seat_number'] = carriage_match.group(2)
        
        return info
    
    def _extract_with_regex(self, text):
        """使用正则表达式提取信息"""
        info = {}
        
        # 提取订单号（支持多种格式）
        # 新格式：订单号码 E673307420
        # 旧格式：订单号码E167803849
        match = re.search(r'订单号[码:]?\s*([A-Z]\d+)', text)
        if match:
            info['order_number'] = match.group(1)
        
        # 提取车次（支持多种格式）
        # 新格式：G4480次列车
        # 旧格式：T164次列车
        match = re.search(r'([GDCKZT]\d+)次(?:列车)?', text)
        if match:
            info['train_number'] = match.group(1)
        
        # 提取出发站和到达站
        # 新格式：郑州东站-北京西站
        # 旧格式：上海—郑州（使用长破折号）
        stations = re.findall(r'([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)\s*[-—→]\s*([\u4e00-\u9fa5]+(?:站|东|西|南|北)?)', text)
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
        
        # 提取出发时间（支持多种格式）
        # 新格式：2026年05月06日02:30开
        # 旧格式：01月24日19:28（没有年份）
        match = re.search(r'(\d{4}年)?(\d{1,2}月\d{1,2}日)\s*(\d{2}:\d{2})开?', text)
        if match:
            year_part = match.group(1)  # 可能为空
            date_part = match.group(2)
            time_part = match.group(3)
            
            if year_part:
                # 有年份：2026年05月06日
                full_date = f"{year_part.rstrip('年')}年{date_part}"
                try:
                    departure_datetime = datetime.strptime(f"{full_date} {time_part}", "%Y年%m月%d日 %H:%M")
                    info['departure_datetime'] = departure_datetime.strftime("%Y-%m-%d %H:%M")
                except:
                    info['departure_datetime'] = f"{full_date} {time_part}"
            else:
                # 没有年份：01月24日（需要从邮件日期推断年份）
                info['departure_date_partial'] = f"{date_part} {time_part}"
                # 暂时保存，后续可能需要结合邮件日期补充年份
                info['departure_datetime'] = f"{date_part} {time_part}"
        
        # 提取价格（支持多种格式）
        # 新格式：票价309.0元
        # 旧格式：票价130.00元
        prices = re.findall(r'票价([\d.]+)元', text)
        if prices:
            # 取最后一个价格（通常是总价）
            info['price'] = float(prices[-1])
        else:
            # 备用：匹配 ¥ 符号
            prices = re.findall(self.patterns['price'], text)
            if prices:
                info['price'] = float(prices[-1])

        info.update(self._extract_financial_fields(text, None))
        
        # 提取座位类型（支持多种格式）
        # 新格式：二等座，成人票
        # 旧格式：硬座
        seat_type = self._extract_seat_type_from_text(text)
        if seat_type:
            info['seat_type'] = seat_type
        
        # 提取乘客姓名（支持多种格式）
        # 格式：1.张三, 或 张三，
        match = re.search(r'\d+\.([\u4e00-\u9fa5·]{2,4})[,，]', text)
        if match:
            info['passenger_name'] = match.group(1)
        else:
            # 备用方案
            match = re.search(self.patterns['passenger_name'], text)
            if match:
                info['passenger_name'] = match.group(1)
        
        # 提取车厢和座位号（新格式特有）
        # 格式：14车8A号 或 11车044号
        match = re.search(r'(\d+)车(\d+[A-Z]?)号', text)
        if match:
            info['carriage'] = match.group(1)  # 车厢号
            info['seat_number'] = match.group(2)  # 座位号
        
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
                                info['seat_type'] = self._normalize_seat_type(cell)
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
