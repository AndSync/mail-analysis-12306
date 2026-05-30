"""
12306邮件分析系统 - 主程序入口
功能：读取12306邮件，分析出行数据，生成HTML报告并发送邮件
"""
import json
import logging
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# 导入engine模块
sys.path.insert(0, os.path.join(BASE_DIR, 'engine'))
from mail_reader import MailReader
from email_parser import EmailParser
from data_analyzer import DataAnalyzer
from html_report import HTMLReportGenerator
from email_sender import EmailSender

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, 'analysis.log'), encoding='utf-8', mode='w')
    ]
)

logger = logging.getLogger(__name__)


def _is_placeholder(value):
    if not value:
        return True
    if isinstance(value, str):
        return value.startswith('your_') or value.endswith('@example.com')
    return False


def _validate_config(config):
    email_cfg = config.get('email', {})
    missing = []
    for key in ('sender_email', 'sender_password', 'recipient_email'):
        value = email_cfg.get(key)
        if key == 'recipient_email':
            if not value or not isinstance(value, list) or not value[0]:
                missing.append(key)
            elif _is_placeholder(value[0]):
                missing.append(key)
        elif _is_placeholder(value):
            missing.append(key)

    if missing:
        logger.error(
            f"邮箱尚未配置（缺少: {', '.join(missing)}）。请编辑:\n  {CONFIG_PATH}\n"
            "填写 email.sender_email、email.sender_password（IMAP 授权码，非登录密码）、"
            "email.recipient_email 后重新运行。"
        )
        return False
    return True


def load_config(config_path=CONFIG_PATH):
    """加载配置文件"""
    if not os.path.exists(config_path):
        logger.error(f"未找到配置文件，请创建并编辑:\n  {config_path}")
        sys.exit(1)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        sys.exit(1)

    if not _validate_config(config):
        sys.exit(1)

    logger.info("配置文件加载成功")
    return config


def main():
    """主函数"""
    logger.info("="*60)
    logger.info("12306邮件分析系统启动")
    logger.info("="*60)
    
    # 加载配置
    config = load_config()
    
    # 步骤1: 读取邮件
    logger.info("\n【步骤1】开始读取12306邮件...")
    mail_reader = MailReader(config)
    
    if not mail_reader.connect():
        logger.error("无法连接到邮箱服务器，程序退出")
        return
    
    try:
        mailbox_name = config.get('analysis', {}).get('mailbox_name', None)
        if mailbox_name == '':
            mailbox_name = None

        if mailbox_name:
            logger.info(f"✓ 当前策略：优先扫描指定文件夹 {mailbox_name}")
        else:
            logger.info("✓ 当前策略：未指定文件夹，默认扫描全邮箱文件夹，再本地筛选 12306 邮件")
        
        # 获取日期范围配置
        analysis_config = config.get('analysis', {})
        start_year = analysis_config.get('start_year')
        end_year = analysis_config.get('end_year')
        start_month = analysis_config.get('start_month')
        end_month = analysis_config.get('end_month')
        max_emails = analysis_config.get('max_emails', 10000)
        
        # 构建日期字符串
        start_date = None
        end_date = None
        
        if start_year and start_month:
            start_date = f"01-{start_month}-{start_year}"
        elif start_year:
            start_date = f"01-Jan-{start_year}"
        
        if end_year and end_month:
            # 获取该月最后一天（简化处理）
            end_date = f"01-{int(end_month.split('-')[1])+1}-{end_month.split('-')[0]}"
        elif end_year:
            end_date = f"31-Dec-{end_year}"
        
        logger.info(f"搜索条件: 开始日期={start_date}, 结束日期={end_date}, 最大数量={max_emails}")
        
        # 搜索并获取邮件
        emails_data = mail_reader.search_12306_emails(
            start_date=start_date,
            end_date=end_date,
            limit=max_emails,
            mailbox_name=mailbox_name
        )
        
        if not emails_data:
            logger.warning("未找到任何12306相关邮件")
            return
        
        logger.info(f"成功获取 {len(emails_data)} 封邮件\n")
        
    finally:
        mail_reader.disconnect()
    
    # 步骤2: 解析邮件
    logger.info("【步骤2】开始解析邮件内容...")
    parser = EmailParser()
    records = parser.parse_emails(emails_data)
    
    if not records:
        logger.warning("未能从邮件中提取到任何票务记录")
        return
    
    logger.info(f"成功解析 {len(records)} 条票务记录\n")
    
    # 步骤3: 数据分析
    logger.info("【步骤3】开始数据分析...")
    analyzer = DataAnalyzer(records)
    
    report_data = analyzer.generate_full_report(
        start_year=start_year,
        end_year=end_year,
        start_month=start_month,
        end_month=end_month
    )
    
    if not report_data:
        logger.warning("分析报告为空")
        return
    
    logger.info("数据分析完成\n")
    
    # 步骤4: 生成HTML报告
    logger.info("【步骤4】生成HTML报告...")
    report_generator = HTMLReportGenerator()
    html_content = report_generator.generate(report_data)
    
    if not html_content:
        logger.error("HTML报告生成失败")
        return
    
    logger.info("HTML报告生成完成\n")
    
    # 步骤5: 发送邮件
    logger.info("【步骤5】发送报告邮件...")
    email_sender = EmailSender(config)
    
    subject = f"12306出行统计报告 ({datetime.now().strftime('%Y-%m-%d')})"
    success = email_sender.send_report(html_content, subject)
    
    if success:
        logger.info("\n" + "="*60)
        logger.info("✅ 所有任务完成！报告已发送到您的邮箱")
        logger.info("="*60)
    else:
        logger.error("\n" + "="*60)
        logger.error("❌ 邮件发送失败")
        logger.info("="*60)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n用户中断程序")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        sys.exit(1)
