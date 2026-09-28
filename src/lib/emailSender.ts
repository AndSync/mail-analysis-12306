/**
 * 邮件发送模块 —— 将 HTML 报告通过 SMTP 发送。
 * 移植自 src/engine/email_sender.py；底层用 nodemailer。
 */

import nodemailer from "nodemailer";
import type { MailConfig } from "./config.js";

export class EmailSender {
  smtpServer: string;
  smtpPort: number;
  senderEmail: string;
  senderPassword: string;
  recipients: string[];

  constructor(config: MailConfig) {
    this.smtpServer = config.smtp_server || "smtp.qq.com";
    this.smtpPort = config.smtp_port || 465;
    this.senderEmail = config.email?.sender_email || "";
    this.senderPassword = config.email?.sender_password || "";
    this.recipients = config.email?.recipient_email || [];
  }

  async sendReport(htmlContent: string, subject = "12306出行统计报告"): Promise<boolean> {
    try {
      const transporter = nodemailer.createTransport({
        host: this.smtpServer,
        port: this.smtpPort,
        secure: true,
        auth: { user: this.senderEmail, pass: this.senderPassword },
      });

      await transporter.sendMail({
        from: this.senderEmail,
        to: this.recipients.join(", "),
        subject,
        html: htmlContent,
      });
      return true;
    } catch {
      return false;
    }
  }
}
