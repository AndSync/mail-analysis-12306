"""
邮件读取模块 - 连接IMAP服务器并获取12306邮件
"""
import imaplib
import email
from email.header import decode_header
import time
import logging

logger = logging.getLogger(__name__)


class MailReader:
    """邮件读取器"""
    
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
    
    def select_mailbox(self, mailbox_name='INBOX'):
        """
        选择邮箱文件夹
        :param mailbox_name: 邮箱文件夹名称
        """
        try:
            # 处理中文文件夹名称编码问题（QQ邮箱使用Modified UTF-7）
            try:
                # 尝试将中文转换为 IMAP 的 UTF-7 编码
                if any(ord(c) > 127 for c in mailbox_name):
                    # 包含中文字符，需要编码
                    mailbox_name_encoded = mailbox_name.encode('utf-7').decode('ascii').replace('+', '&').rstrip('=')
                    logger.debug(f"文件夹名称编码: {mailbox_name} -> {mailbox_name_encoded}")
                    status, messages = self.mailbox.select(mailbox_name_encoded)
                else:
                    status, messages = self.mailbox.select(mailbox_name)
            except Exception as encode_error:
                logger.debug(f"文件夹名称编码失败，使用原始名称: {encode_error}")
                status, messages = self.mailbox.select(mailbox_name)
            
            if status == 'OK':
                logger.info(f"已选择邮箱文件夹: {mailbox_name}, 邮件数量: {messages[0]}")
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
            return mailbox_list
        except Exception as e:
            logger.error(f"获取文件夹列表异常: {e}")
            return []
    
    def search_12306_emails_in_mailbox(self, mailbox_name, start_date=None, end_date=None, limit=None):
        """
        在指定文件夹中搜索12306相关邮件
        :param mailbox_name: 文件夹名称
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param limit: 最大获取邮件数量
        :return: 邮件列表
        """
        emails_data = []
        
        try:
            # 选择文件夹
            status, messages = self.mailbox.select(mailbox_name)
            if status != 'OK':
                logger.warning(f"无法选择文件夹 {mailbox_name}，跳过")
                return emails_data
            
            mail_count = int(messages[0])
            if mail_count == 0:
                logger.debug(f"文件夹 {mailbox_name} 中没有邮件")
                return emails_data
            
            # 构建搜索条件 - 通过发件人过滤12306邮件
            # 注意：IMAP协议不支持中文搜索条件，只能使用英文
            # 默认搜索发件人 12306@rails.com.cn
            search_criteria = '(FROM "12306@rails.com.cn")'
            
            if start_date and end_date:
                search_criteria = f'(SINCE "{start_date}" BEFORE "{end_date}" {search_criteria})'
            elif start_date:
                search_criteria = f'(SINCE "{start_date}" {search_criteria})'
            elif end_date:
                search_criteria = f'(BEFORE "{end_date}" {search_criteria})'
            
            logger.debug(f"搜索条件: {search_criteria}")
            status, messages = self.mailbox.search(None, search_criteria)
            
            if status != 'OK':
                logger.warning(f"在文件夹 {mailbox_name} 中搜索失败")
                return emails_data
            
            email_ids = messages[0].split()
            if not email_ids:
                return emails_data
            
            total_emails = len(email_ids)
            logger.info(f"文件夹 {mailbox_name}: 找到 {total_emails} 封12306相关邮件")
            
            # 限制处理数量
            if limit and total_emails > limit:
                email_ids = email_ids[-limit:]
                logger.info(f"文件夹 {mailbox_name}: 限制处理 {len(email_ids)} 封邮件")
            
            for idx, email_id in enumerate(email_ids):
                try:
                    status, msg_data = self.mailbox.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK':
                        continue
                    
                    raw_email = msg_data[0][1]
                    email_message = email.message_from_bytes(raw_email)
                    
                    # 解析邮件内容
                    email_data = self._parse_email(email_message)
                    
                    if email_data:
                        emails_data.append(email_data)
                    
                    # 每处理50封邮件打印一次进度
                    if (idx + 1) % 50 == 0:
                        logger.info(f"已处理 {idx + 1}/{len(email_ids)} 封邮件")
                    
                    # 避免请求过快
                    time.sleep(0.02)
                    
                except Exception as e:
                    logger.error(f"处理邮件 {email_id} 时出错: {e}")
                    continue
            
            logger.info(f"文件夹 {mailbox_name}: 成功解析 {len(emails_data)} 封有效邮件")
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
        
        # 如果指定了文件夹，只搜索该文件夹
        if mailbox_name:
            logger.info(f"在指定文件夹 '{mailbox_name}' 中搜索...")
            all_emails_data = self.search_12306_emails_in_mailbox(
                mailbox_name, start_date, end_date, limit
            )
        else:
            # 默认搜索收件箱（INBOX）
            logger.info("未指定文件夹，搜索收件箱（INBOX）...")
            all_emails_data = self.search_12306_emails_in_mailbox(
                'INBOX', start_date, end_date, limit
            )
            
            # 如果收件箱没有找到，尝试搜索所有文件夹
            if not all_emails_data:
                logger.info("收件箱未找到邮件，尝试搜索所有文件夹...")
                mailboxes = self.list_all_mailboxes()
                
                if not mailboxes:
                    logger.error("无法获取文件夹列表")
                    return all_emails_data
                
                total_processed = 0
                for idx, mailbox in enumerate(mailboxes):
                    # 跳过已经搜索过的 INBOX
                    if mailbox == 'INBOX':
                        continue
                    
                    logger.info(f"\n正在搜索文件夹 [{idx+1}/{len(mailboxes)}]: {mailbox}")
                    
                    # 计算当前文件夹的限制数量
                    remaining_limit = limit - len(all_emails_data) if limit else None
                    
                    if remaining_limit is not None and remaining_limit <= 0:
                        logger.info(f"已达到邮件数量限制 {limit}，停止搜索")
                        break
                    
                    folder_emails = self.search_12306_emails_in_mailbox(
                        mailbox, start_date, end_date, remaining_limit
                    )
                    
                    all_emails_data.extend(folder_emails)
                    total_processed += 1
                    
                    logger.info(f"累计获取 {len(all_emails_data)} 封邮件")
                    
                    # 文件夹之间稍作延迟
                    if idx < len(mailboxes) - 1:
                        time.sleep(0.5)
                
                logger.info(f"\n共搜索 {total_processed} 个文件夹")
        
        logger.info(f"\n总计成功解析 {len(all_emails_data)} 封有效邮件")
        return all_emails_data
    
    def _parse_email(self, email_message):
        """
        解析单封邮件
        :param email_message: 邮件对象
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
            body = self._get_email_body(email_message)
            
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
    
    def _get_email_body(self, email_message):
        """
        获取邮件正文
        :param email_message: 邮件对象
        :return: 邮件正文字符串
        """
        body = ""
        
        if email_message.is_multipart():
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
