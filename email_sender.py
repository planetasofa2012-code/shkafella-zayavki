"""
Отправка заявки по email с вложениями.
Используется стандартный SMTP (Yandex, Gmail, Mail.ru и т.д.)
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL

logger = logging.getLogger(__name__)


async def send_application_email(bot, data: dict) -> bool:
    """
    Отправить заявку на email клиента.
    Скачивает файлы из Telegram и прикрепляет к письму.
    
    Возвращает True если отправлено успешно.
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = RECIPIENT_EMAIL
        msg["Subject"] = f"Новая заявка — {data.get('company', '?')} / {data.get('order_name', '?')}"

        # Тело письма
        body = _format_body(data)
        msg.attach(MIMEText(body, "html", "utf-8"))

        # Прикрепляем файлы из Telegram
        files_data = data.get("files", [])
        for f in files_data:
            try:
                tg_file = await bot.get_file(f["file_id"])
                file_io = await bot.download_file(tg_file.file_path)
                file_bytes = file_io.read()
                filename = f.get("file_name", "file")

                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(file_bytes)
                encoders.encode_base64(attachment)
                attachment.add_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{filename}\"",
                )
                msg.attach(attachment)

            except Exception as e:
                logger.warning(f"Не удалось прикрепить файл {f.get('file_name')}: {e}")

        # Отправляем через SMTP
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)

        logger.info(f"Заявка отправлена на {RECIPIENT_EMAIL}: {data.get('company')}")
        return True

    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}", exc_info=True)
        return False


def _format_body(data: dict) -> str:
    """Сформировать HTML-тело письма."""
    files_count = len(data.get("files", []))
    telegram_user = data.get("telegram_user", "—")

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2c3e50;">📋 Новая заявка на раскрой</h2>
        
        <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Компания</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{data.get('company', '—')}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Заказ / Клиент</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{data.get('order_name', '—')}</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Услуга</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;"><b>{data.get('service', '—')}</b></td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Файлов</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{files_count} (прикреплены к письму)</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Комментарий</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{data.get('comment', '—')}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Дата готовности</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{data.get('deadline', '—')}</td>
            </tr>
            <tr style="background: #f8f9fa;">
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Telegram</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{telegram_user}</td>
            </tr>
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Дата заявки</td>
                <td style="padding: 10px; border: 1px solid #dee2e6;">{data.get('date', '—')}</td>
            </tr>
        </table>
        
        <p style="color: #7f8c8d; margin-top: 20px; font-size: 12px;">
            Отправлено ботом заявок Шкафелла
        </p>
    </body>
    </html>
    """
