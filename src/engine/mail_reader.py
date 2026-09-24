"""
邮件读取模块 - 连接IMAP服务器并获取12306邮件
"""
import imaplib
import email
from email.header import decode_header
import time
import logging
import base64

logger = logging.getLogger(__name__)


class MailReader:
    """邮件读取器"""

    TRUST_MAILBOX_BATCH_SIZE = 40
    HEADER_BATCH_SIZE = 120
    
    def __init__(self, config):
        """
        初始化邮件读取器
        :param config: 配置字典，包含邮箱服务器信息
        """
        self.imap_server = config.get('imap_server', 'imap.qq.com')
        self.imap_port = config.get('imap_port', 993)
        self.username = config['email']['sender_email']
        self.password = config['email']['sender_password']
        self.mailbox = None
        self._mailboxes_cache = None
    
    def connect(self):
        """连接到IMAP服务器"""
        try:
            logger.info(f"正在连接到 {self.imap_server}...")
            self.mailbox = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.mailbox.login(self.username, self.password)
            logger.info("登录成功")
            return True
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.mailbox:
            self.mailbox.logout()
            logger.info("已断开连接")

    def _encode_mailbox_name(self, mailbox_name):
        """将文件夹名编码为 IMAP Modified UTF-7"""
        if not mailbox_name:
            return mailbox_name

        result = []
        buffer = []

        def flush_buffer():
            if not buffer:
                return
            raw = ''.join(buffer).encode('utf-16-be')
            encoded = base64.b64encode(raw).decode('ascii').rstrip('=').replace('/', ',')
            result.append(f"&{encoded}-")
            buffer.clear()

        for char in mailbox_name:
            code = ord(char)
            if 0x20 <= code <= 0x7E and char != '&':
                flush_buffer()
                result.append(char)
            elif char == '&':
                flush_buffer()
                result.append('&-')
            else:
                buffer.append(char)

        flush_buffer()
        return ''.join(result)

    def _decode_mailbox_name(self, mailbox_name):
        """将 IMAP Modified UTF-7 解码为可读文件夹名"""
        if not mailbox_name or '&' not in mailbox_name:
            return mailbox_name

        result = []
        i = 0
        length = len(mailbox_name)

        while i < length:
            char = mailbox_name[i]
            if char != '&':
                result.append(char)
                i += 1
                continue

            end = mailbox_name.find('-', i)
            if end == -1:
                result.append(mailbox_name[i:])
                break

            token = mailbox_name[i + 1:end]
            if token == '':
                result.append('&')
            else:
                token = token.replace(',', '/')
                padding = '=' * ((4 - len(token) % 4) % 4)
                decoded = base64.b64decode(token + padding)
                result.append(decoded.decode('utf-16-be'))
            i = end + 1

        return ''.join(result)

    def _get_mailbox_aliases(self, mailbox_name):
        """返回可用于匹配的多个文件夹别名"""
        aliases = {mailbox_name}
        if mailbox_name:
            aliases.add(self._encode_mailbox_name(mailbox_name))
            aliases.add(self._decode_mailbox_name(mailbox_name))
            if '/' in mailbox_name:
                aliases.add(mailbox_name.split('/')[-1])
        return {alias for alias in aliases if alias}

    def _resolve_mailbox_name(self, mailbox_name):
        """
        解析文件夹名称，兼容中文名、IMAP 编码名和 QQ 邮箱返回的实际名称
        :return: (display_name, server_name)
        """
        mailboxes = self._mailboxes_cache or self.list_all_mailboxes()
        self._mailboxes_cache = mailboxes

        candidates = list(self._get_mailbox_aliases(mailbox_name))

        for candidate in candidates:
            if candidate in mailboxes:
                return mailbox_name, candidate

        for existing in mailboxes:
            decoded_existing = self._decode_mailbox_name(existing)
            existing_aliases = self._get_mailbox_aliases(decoded_existing) | {existing}
            if any(existing.endswith(candidate) for candidate in candidates):
                return decoded_existing, existing
            if candidates and existing_aliases.intersection(candidates):
                return decoded_existing, existing

        return mailbox_name, self._encode_mailbox_name(mailbox_name)

    def _build_search_criteria(self, start_date=None, end_date=None):
        """构建搜索条件，避免使用 FROM 服务端过滤导致老邮件漏查"""
        filters = []
        if start_date:
            filters.append(f'SINCE "{start_date}"')
        if end_date:
            filters.append(f'BEFORE "{end_date}"')

        if not filters:
            return 'ALL'

        if len(filters) == 1:
            return filters[0]

        return f"({' '.join(filters)})"

    def _is_12306_email(self, email_data):
        """在本地判断是否为 12306 相关邮件"""
        if not email_data:
            return False

        from_addr = (email_data.get('from') or '').lower()
        subject = email_data.get('subject') or ''
        body = email_data.get('body') or ''
        text = f"{subject}\n{body}".lower()

        sender_keywords = [
            '12306@rails.com.cn',
            '12306.cn',
            '中国铁路客户服务中心',
        ]
        text_keywords = [
            '12306',
            '订票',
            '购票',
            '出票',
            '退票',
            '改签',
            '候补',
            '车次',
            '席别',
            '订单号',
        ]

        if any(keyword in from_addr for keyword in sender_keywords):
            return True

        if '12306' in from_addr:
            return True

        return any(keyword in text for keyword in text_keywords)

    def _fetch_email_headers(self, email_id):
        """仅获取邮件头，便于快速过滤候选邮件"""
        try:
            status, msg_data = self.mailbox.fetch(
                email_id,
                '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])'
            )
            if status != 'OK' or not msg_data or not msg_data[0]:
                return None

            raw_header = msg_data[0][1]
            if not raw_header:
                return None

            header_message = email.message_from_bytes(raw_header)
            return {
                'subject': self._decode_header_value(header_message['Subject']),
                'from': self._decode_header_value(header_message['From']),
                'date': header_message['Date'] or '',
                'body': ''
            }
        except Exception as e:
            logger.debug(f"获取邮件头失败 {email_id}: {e}")
            return None

    def _fetch_email_headers_batch(self, email_ids):
        """批量获取邮件头"""
        if not email_ids:
            return []

        ids = []
        for email_id in email_ids:
            if isinstance(email_id, bytes):
                ids.append(email_id.decode('ascii', errors='ignore'))
            else:
                ids.append(str(email_id))

        status, msg_data = self.mailbox.fetch(
            ','.join(ids),
            '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])'
        )
        if status != 'OK' or not msg_data:
            return []

        headers = []
        for item in msg_data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue

            raw_header = item[1]
            if not isinstance(raw_header, (bytes, bytearray)) or not raw_header:
                continue

            try:
                header_message = email.message_from_bytes(raw_header)
                headers.append({
                    'subject': self._decode_header_value(header_message['Subject']),
                    'from': self._decode_header_value(header_message['From']),
                    'date': header_message['Date'] or '',
                    'body': ''
                })
            except Exception as e:
                logger.debug(f"批量获取邮件头失败: {e}")

        return headers

    def _fetch_full_email(self, email_id, fast_body=False):
        """获取完整邮件内容"""
        status, msg_data = self.mailbox.fetch(email_id, '(RFC822)')
        if status != 'OK' or not msg_data or not msg_data[0]:
            return None

        raw_email = msg_data[0][1]
        if not raw_email:
            return None

        email_message = email.message_from_bytes(raw_email)
        return self._parse_email(email_message, fast_body=fast_body)

    def _chunk_email_ids(self, email_ids, chunk_size):
        """按批次拆分邮件ID"""
        for start in range(0, len(email_ids), chunk_size):
            yield email_ids[start:start + chunk_size]

    def _fetch_full_emails_batch(self, email_ids, fast_body=False):
        """批量获取完整邮件内容"""
        if not email_ids:
            return []

        ids = []
        for email_id in email_ids:
            if isinstance(email_id, bytes):
                ids.append(email_id.decode('ascii', errors='ignore'))
            else:
                ids.append(str(email_id))

        status, msg_data = self.mailbox.fetch(','.join(ids), '(RFC822)')
        if status != 'OK' or not msg_data:
            return []

        emails_data = []
        for item in msg_data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue

            raw_email = item[1]
            if not isinstance(raw_email, (bytes, bytearray)) or not raw_email:
                continue

            try:
                email_message = email.message_from_bytes(raw_email)
                email_data = self._parse_email(email_message, fast_body=fast_body)
                if email_data:
                    emails_data.append(email_data)
            except Exception as e:
                logger.error(f"批量解析邮件失败: {e}")

        return emails_data
    
    def select_mailbox(self, mailbox_name='INBOX'):
        """
        选择邮箱文件夹
        :param mailbox_name: 邮箱文件夹名称
        """
        try:
            display_name, server_name = self._resolve_mailbox_name(mailbox_name)
            status, messages = self.mailbox.select(server_name, readonly=True)
            
            if status == 'OK':
                logger.info(f"已选择邮箱文件夹: {display_name} [{server_name}], 邮件数量: {messages[0]}")
                return int(messages[0])
            else:
                logger.error(f"选择邮箱文件夹失败: {messages}")
                return 0
        except Exception as e:
            logger.error(f"选择邮箱文件夹异常: {e}")
            return 0
    
    def list_all_mailboxes(self):
        """
        获取所有邮箱文件夹列表
        :return: 文件夹名称列表
        """
        try:
            status, mailboxes = self.mailbox.list()
            if status != 'OK':
                logger.error("获取文件夹列表失败")
                return []
            
            mailbox_list = []
            for mailbox in mailboxes:
                # 解析文件夹名称（格式: "(\HasNoChildren) "/" "FolderName"）
                if isinstance(mailbox, bytes):
                    mailbox_str = mailbox.decode('utf-8', errors='ignore')
                else:
                    mailbox_str = str(mailbox)
                
                # 提取文件夹名称
                parts = mailbox_str.split('"')
                if len(parts) >= 3:
                    folder_name = parts[-2]
                    # 跳过一些系统文件夹
                    if folder_name and not folder_name.startswith('[Gmail]'):
                        mailbox_list.append(folder_name)
            
            logger.info(f"找到 {len(mailbox_list)} 个文件夹: {mailbox_list}")
            self._mailboxes_cache = mailbox_list
            return mailbox_list
        except Exception as e:
            logger.error(f"获取文件夹列表异常: {e}")
            return []
    
    def search_12306_emails_in_mailbox(self, mailbox_name, start_date=None, end_date=None, limit=None, trust_mailbox=False):
        """
        在指定文件夹中搜索12306相关邮件
        :param mailbox_name: 文件夹名称
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param limit: 最大获取邮件数量
        :param trust_mailbox: 是否信任该文件夹基本都是12306邮件；为True时跳过头部预筛
        :return: 邮件列表
        """
        emails_data = []
        
        try:
            # 选择文件夹
            display_name, server_name = self._resolve_mailbox_name(mailbox_name)
            status, messages = self.mailbox.select(server_name, readonly=True)
            if status != 'OK':
                logger.warning(f"无法选择文件夹 {display_name} [{server_name}]，跳过")
                return emails_data
            
            mail_count = int(messages[0])
            if mail_count == 0:
                logger.debug(f"文件夹 {mailbox_name} 中没有邮件")
                return emails_data
            
            search_criteria = self._build_search_criteria(start_date, end_date)
            
            logger.debug(f"搜索条件: {search_criteria}")
            status, messages = self.mailbox.search(None, search_criteria)
            
            if status != 'OK':
                logger.warning(f"在文件夹 {display_name} 中搜索失败")
                return emails_data
            
            email_ids = messages[0].split()
            if not email_ids:
                return emails_data
            
            total_emails = len(email_ids)
            logger.info(f"文件夹 {display_name}: 服务端命中 {total_emails} 封候选邮件")
            
            # 限制处理数量
            if limit and total_emails > limit:
                email_ids = email_ids[-limit:]
                logger.info(f"文件夹 {display_name}: 限制处理 {len(email_ids)} 封候选邮件")
            
            if trust_mailbox:
                candidate_ids = email_ids
                logger.info(f"文件夹 {display_name}: 已启用指定文件夹直读模式，跳过头部预筛")
            else:
                candidate_ids = []
                processed = 0
                for batch_ids in self._chunk_email_ids(email_ids, self.HEADER_BATCH_SIZE):
                    try:
                        header_batch = self._fetch_email_headers_batch(batch_ids)
                        for email_id, header_data in zip(batch_ids, header_batch):
                            if header_data and self._is_12306_email(header_data):
                                candidate_ids.append(email_id)

                        processed += len(batch_ids)
                        logger.info(f"已扫描头部 {processed}/{len(email_ids)} 封邮件")
                        time.sleep(0.002)
                    except Exception as e:
                        logger.error(f"批量扫描邮件头时出错: {e}")
                        continue

                logger.info(f"文件夹 {display_name}: 头部筛出 {len(candidate_ids)} 封12306候选邮件")

            if trust_mailbox:
                processed = 0
                for batch_ids in self._chunk_email_ids(candidate_ids, self.TRUST_MAILBOX_BATCH_SIZE):
                    try:
                        batch_emails = self._fetch_full_emails_batch(batch_ids, fast_body=True)
                        emails_data.extend(batch_emails)
                        processed += len(batch_ids)
                        logger.info(f"已批量获取正文 {processed}/{len(candidate_ids)} 封邮件")
                    except Exception as e:
                        logger.error(f"批量获取完整邮件失败: {e}")
            else:
                for idx, email_id in enumerate(candidate_ids):
                    try:
                        email_data = self._fetch_full_email(email_id, fast_body=False)
                        if email_data and self._is_12306_email(email_data):
                            emails_data.append(email_data)

                        if (idx + 1) % 50 == 0:
                            logger.info(f"已获取正文 {idx + 1}/{len(candidate_ids)} 封邮件")

                        time.sleep(0.01)
                    except Exception as e:
                        logger.error(f"获取完整邮件 {email_id} 时出错: {e}")
                        continue
            
            logger.info(f"文件夹 {display_name}: 成功筛出 {len(emails_data)} 封12306有效邮件")
            return emails_data
            
        except Exception as e:
            logger.error(f"在文件夹 {mailbox_name} 中搜索异常: {e}")
            return emails_data
    
    def search_12306_emails(self, start_date=None, end_date=None, limit=10000, mailbox_name=None):
        """
        搜索12306相关邮件（支持单个或多个文件夹）
        :param start_date: 开始日期，格式: "01-Jan-2020"
        :param end_date: 结束日期，格式: "31-Dec-2024"
        :param limit: 最大获取邮件数量
        :param mailbox_name: 文件夹名称，如果为None则搜索收件箱
        :return: 邮件列表
        """
        all_emails_data = []
        seen_keys = set()

        def extend_unique(items):
            for item in items:
                key = (
                    item.get('date') or '',
                    item.get('subject') or '',
                    item.get('from') or '',
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_emails_data.append(item)

        if mailbox_name:
            logger.info(f"开始搜索指定文件夹: {mailbox_name}")
            extend_unique(self.search_12306_emails_in_mailbox(
                mailbox_name, start_date, end_date, limit, trust_mailbox=True
            ))
        else:
            logger.info("开始搜索所有文件夹（含 INBOX）...")
            mailboxes = self.list_all_mailboxes()

            if not mailboxes:
                logger.error("无法获取文件夹列表")
                return all_emails_data

            ordered_mailboxes = ['INBOX'] + [box for box in mailboxes if box != 'INBOX']
            total_processed = 0

            for idx, mailbox in enumerate(ordered_mailboxes):
                logger.info(f"\n正在搜索文件夹 [{idx + 1}/{len(ordered_mailboxes)}]: {mailbox}")

                remaining_limit = limit - len(all_emails_data) if limit else None
                if remaining_limit is not None and remaining_limit <= 0:
                    logger.info(f"已达到邮件数量限制 {limit}，停止搜索")
                    break

                folder_emails = self.search_12306_emails_in_mailbox(
                    mailbox, start_date, end_date, remaining_limit, trust_mailbox=False
                )

                extend_unique(folder_emails)
                total_processed += 1
                logger.info(f"累计获取 {len(all_emails_data)} 封邮件")

                if idx < len(ordered_mailboxes) - 1:
                    time.sleep(0.2)

            logger.info(f"\n共搜索 {total_processed} 个文件夹")
        
        logger.info(f"\n总计成功解析 {len(all_emails_data)} 封有效邮件")
        return all_emails_data
    
    def _parse_email(self, email_message, fast_body=False):
        """
        解析单封邮件
        :param email_message: 邮件对象
        :param fast_body: 是否使用更快的正文提取路径
        :return: 解析后的邮件数据字典
        """
        try:
            # 获取邮件主题
            subject = self._decode_header_value(email_message['Subject'])
            
            # 获取发件人
            from_addr = self._decode_header_value(email_message['From'])
            
            # 获取日期
            date = email_message['Date']
            
            # 获取邮件正文
            body = self._get_email_body(email_message, fast_mode=fast_body)
            
            return {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body
            }
            
        except Exception as e:
            logger.error(f"解析邮件失败: {e}")
            return None
    
    def _decode_header_value(self, header_value):
        """解码邮件头"""
        if not header_value:
            return ""
        
        decoded_parts = decode_header(header_value)
        decoded_str = ""
        
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                decoded_str += part.decode(charset or 'utf-8', errors='ignore')
            else:
                decoded_str += part
        
        return decoded_str
    
    def _get_email_body(self, email_message, fast_mode=False):
        """
        获取邮件正文
        :param email_message: 邮件对象
        :param fast_mode: 是否使用更快的正文提取路径
        :return: 邮件正文字符串
        """
        body = ""
        
        if email_message.is_multipart():
            if fast_mode:
                html_payload = None
                text_payload = None
                for part in email_message.walk():
                    content_disposition = str(part.get("Content-Disposition"))
                    if "attachment" in content_disposition:
                        continue

                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    content_type = part.get_content_type()
                    if content_type == "text/html" and html_payload is None:
                        html_payload = payload
                        break
                    if content_type == "text/plain" and text_payload is None:
                        text_payload = payload

                if html_payload:
                    return self._decode_with_fallback(html_payload)
                if text_payload:
                    return self._decode_with_fallback(text_payload)
                return ""

            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                # 优先获取HTML内容
                if content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # 尝试多种编码
                            body = self._decode_with_fallback(payload)
                            if body:
                                break
                    except Exception as e:
                        logger.debug(f"解析HTML部分失败: {e}")
                        continue
                
                # 其次获取纯文本
                if content_type == "text/plain" and not body:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = self._decode_with_fallback(payload)
                    except Exception as e:
                        logger.debug(f"解析文本部分失败: {e}")
                        continue
        else:
            # 非多部分邮件
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    body = self._decode_with_fallback(payload)
            except Exception as e:
                logger.debug(f"解析邮件正文失败: {e}")
                body = ""
        
        return body
    
    def _decode_with_fallback(self, data):
        """
        尝试多种编码解码数据
        :param data: 字节数据
        :return: 解码后的字符串
        """
        if not data:
            return ""
        
        # 尝试常见编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
        
        for encoding in encodings:
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        
        # 最后使用 utf-8 并忽略错误
        return data.decode('utf-8', errors='ignore')
