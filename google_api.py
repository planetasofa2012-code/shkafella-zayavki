"""
Интеграция с Google Sheets и Google Drive.
Загрузка файлов на Диск, запись заявок в таблицу.
"""

import os
import logging
import tempfile
from io import BytesIO

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, GOOGLE_DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)

# Области доступа Google API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Глобальные клиенты (инициализируются один раз)
_sheets_client = None
_drive_service = None


def _init_google():
    """Инициализация Google API клиентов."""
    global _sheets_client, _drive_service

    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        logger.warning(f"Файл {GOOGLE_CREDENTIALS_FILE} не найден. Google API отключён.")
        return False

    try:
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
        _sheets_client = gspread.authorize(creds)
        _drive_service = build("drive", "v3", credentials=creds)
        logger.info("Google API подключён")
        return True
    except Exception as e:
        logger.error(f"Ошибка инициализации Google API: {e}")
        return False


def _ensure_init():
    """Проверка что Google API инициализирован."""
    if _sheets_client is None or _drive_service is None:
        return _init_google()
    return True


def upload_file_to_drive(file_bytes: bytes, filename: str, subfolder_name: str = "") -> str:
    """
    Загрузить файл на Google Drive.
    Возвращает ссылку на файл.
    """
    if not _ensure_init():
        return ""

    try:
        parent_id = GOOGLE_DRIVE_FOLDER_ID

        # Создаём подпапку для заявки (если указана)
        if subfolder_name:
            folder_meta = {
                "name": subfolder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = _drive_service.files().create(body=folder_meta, fields="id").execute()
            parent_id = folder["id"]

        # Сохраняем файл во временную папку
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Загружаем на Drive
        file_meta = {
            "name": filename,
            "parents": [parent_id],
        }
        media = MediaFileUpload(tmp_path)
        uploaded = _drive_service.files().create(
            body=file_meta, media_body=media, fields="id,webViewLink"
        ).execute()

        # Делаем файл доступным по ссылке
        _drive_service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        # Удаляем временный файл
        os.unlink(tmp_path)

        link = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{uploaded['id']}")
        logger.info(f"Файл загружен: {filename} → {link}")
        return link

    except Exception as e:
        logger.error(f"Ошибка загрузки на Drive: {e}")
        return ""


async def upload_files_to_drive(bot, files_data: list, folder_name: str) -> list:
    """
    Загрузить список файлов из Telegram на Google Drive.
    Возвращает список ссылок.
    """
    if not _ensure_init():
        return []

    links = []

    # Создаём подпапку для этой заявки
    parent_id = GOOGLE_DRIVE_FOLDER_ID
    try:
        folder_meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = _drive_service.files().create(body=folder_meta, fields="id,webViewLink").execute()
        subfolder_id = folder["id"]

        # Делаем папку доступной по ссылке
        _drive_service.permissions().create(
            fileId=subfolder_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        folder_link = folder.get("webViewLink", f"https://drive.google.com/drive/folders/{subfolder_id}")

    except Exception as e:
        logger.error(f"Ошибка создания папки: {e}")
        return []

    # Загружаем файлы
    for f in files_data:
        try:
            tg_file = await bot.get_file(f["file_id"])
            file_io = await bot.download_file(tg_file.file_path)
            file_bytes = file_io.read()

            filename = f.get("file_name", "file")

            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            file_meta = {
                "name": filename,
                "parents": [subfolder_id],
            }
            media = MediaFileUpload(tmp_path)
            _drive_service.files().create(body=file_meta, media_body=media).execute()

            os.unlink(tmp_path)
            logger.info(f"Файл загружен: {filename}")

        except Exception as e:
            logger.error(f"Ошибка загрузки файла {f.get('file_name')}: {e}")

    # Возвращаем одну ссылку на папку (вместо ссылок на каждый файл)
    links.append(folder_link)
    return links


def append_application_to_sheet(row_data: dict):
    """
    Добавить строку заявки в Google Таблицу.
    """
    if not _ensure_init():
        logger.warning("Google Sheets недоступен — заявка не записана")
        return

    try:
        sheet = _sheets_client.open_by_key(GOOGLE_SHEET_ID).sheet1

        # Проверяем заголовки (создаём если таблица пустая)
        headers = [
            "Дата", "Компания", "Заказ/Клиент", "Услуга",
            "Файлы", "Комментарий", "Дата готовности",
            "Telegram", "Telegram ID",
        ]
        try:
            existing_headers = sheet.row_values(1)
            if not existing_headers:
                sheet.append_row(headers)
        except Exception:
            sheet.append_row(headers)

        # Добавляем данные
        row = [
            row_data.get("date", ""),
            row_data.get("company", ""),
            row_data.get("order_name", ""),
            row_data.get("service", ""),
            row_data.get("files", ""),
            row_data.get("comment", ""),
            row_data.get("deadline", ""),
            row_data.get("telegram_user", ""),
            row_data.get("telegram_id", ""),
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"Заявка записана в таблицу: {row_data.get('company')}")

    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")
        raise
