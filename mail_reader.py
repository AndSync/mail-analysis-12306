"""
邮件读取模块 - 连接IMAP服务器并获取12306邮件
"""
import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
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
    
    def search_12306_emails(self, start_date=None, end_date=None, limit=10000):
        """
        搜索12306相关邮件
        :param start_date: 开始日期，格式: "01-Jan-2020"
        :param end_date: 结束日期，格式: "31-Dec-2024"
        :param limit: 最大获取邮件数量
        :return: 邮件列表
        """
        emails_data = []
        
        try:
            # 构建搜索条件
            search_criteria = '(FROM "12306" OR FROM "notifications@12306.cn" OR SUBJECT "12306")'
            
            if start_date and end_date:
                search_criteria = f'(SINCE "{start_date}" BEFORE "{end_date}" {search_criteria})'
            elif start_date:
                search_criteria = f'(SINCE "{start_date}" {search_criteria})'
            elif end_date:
                search_criteria = f'(BEFORE "{end_date}" {search_criteria})'
            
            logger.info(f"搜索条件: {search_criteria}")
            
            status, messages = self.mailbox.search(None, search_criteria)
            
            if status != 'OK':
                logger.error("搜索邮件失败")
                return emails_data
            
            email_ids = messages[0].split()
            total_emails = len(email_ids)
            logger.info(f"找到 {total_emails} 封12306相关邮件")
            
            # 限制处理数量
            email_ids = email_ids[-limit:] if limit else email_ids
            
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
                    
                    # 每处理100封邮件打印一次进度
                    if (idx + 1) % 100 == 0:
                        logger.info(f"已处理 {idx + 1}/{len(email_ids)} 封邮件")
                    
                    # 避免请求过快
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"处理邮件 {email_id} 时出错: {e}")
                    continue
            
            logger.info(f"成功解析 {len(emails_data)} 封有效邮件")
            return emails_data
            
        except Exception as e:
            logger.error(f"搜索邮件异常: {e}")
            return emails_data
    
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
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
                    except:
                        continue
                
                # 其次获取纯文本
                if content_type == "text/plain" and not body:
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        continue
        else:
            # 非多部分邮件
            content_type = email_message.get_content_type()
            try:
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            except:
                body = ""
        
        return body
