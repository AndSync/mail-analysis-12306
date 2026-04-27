"""
邮件发送模块 - 将HTML报告通过邮件发送
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)


class EmailSender:
    """邮件发送器"""
    
    def __init__(self, config):
        """
        初始化邮件发送器
        :param config: 配置字典
        """
        self.smtp_server = config.get('smtp_server', 'smtp.qq.com')
        self.smtp_port = config.get('smtp_port', 465)
        self.sender_email = config['email']['sender_email']
        self.sender_password = config['email']['sender_password']
        self.recipients = config['email']['recipient_email']
    
    def send_report(self, html_content, subject="12306出行统计报告"):
        """
        发送HTML报告邮件
        :param html_content: HTML内容
        :param subject: 邮件主题
        :return: 是否发送成功
        """
        try:
            logger.info("开始发送邮件...")
            
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = subject
            
            # 添加HTML内容
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # 连接SMTP服务器并发送
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.recipients, msg.as_string())
            server.quit()
            
            logger.info(f"邮件发送成功! 收件人: {', '.join(self.recipients)}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    def send_with_attachment(self, html_content, subject="12306出行统计报告", 
                            attachment_path=None):
        """
        发送带附件的邮件
        :param html_content: HTML内容
        :param subject: 邮件主题
        :param attachment_path: 附件路径（可选）
        :return: 是否发送成功
        """
        try:
            logger.info("开始发送邮件（带附件）...")
            
            # 创建邮件对象
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = subject
            
            # 添加HTML内容
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # 如果有附件，添加附件
            if attachment_path:
                from email.mime.base import MIMEBase
                from email import encoders
                import os
                
                with open(attachment_path, 'rb') as f:
                    attachment = MIMEBase('application', 'octet-stream')
                    attachment.set_payload(f.read())
                    encoders.encode_base64(attachment)
                    
                    filename = os.path.basename(attachment_path)
                    attachment.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{filename}"'
                    )
                    msg.attach(attachment)
                    logger.info(f"已添加附件: {filename}")
            
            # 连接SMTP服务器并发送
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.recipients, msg.as_string())
            server.quit()
            
            logger.info(f"邮件发送成功! 收件人: {', '.join(self.recipients)}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
