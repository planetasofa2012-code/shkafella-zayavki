"""
Бот приёма заявок на мебельный раскрой.
Собирает данные → загружает файлы на Google Drive →
отправляет в Telegram менеджеру и записывает в Google Таблицу.
"""

import logging
import tempfile
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaDocument
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import BOT_TOKEN, SERVICES, MAX_FILES

MANAGER_TELEGRAM_ID = os.getenv("MANAGER_TELEGRAM_ID", "")

# ─── Логирование ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Google API ───────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SHEET_ID = "1ovh6v9mNXUTBtJlyNbf3e6a1XoP_9jd4Qxe48KFlZCg"
ROOT_FOLDER_NAME = "Заявки_Шкафелла_Бот"

worksheet = None
drive_service = None
root_folder_id = None

try:
    if os.path.exists("credentials.json"):
        credentials = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
        # Google Sheets
        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.sheet1
        logger.info("Google Sheets подключён!")

        # Google Drive
        drive_service = build("drive", "v3", credentials=credentials)
        logger.info("Google Drive подключён!")
    else:
        logger.warning("Файл credentials.json не найден.")
except Exception as e:
    logger.error(f"Ошибка подключения к Google API: {e}")


def get_or_create_root_folder():
    """Находит или создаёт корневую папку для всех заявок на Диске сервис-аккаунта."""
    global root_folder_id
    if root_folder_id:
        return root_folder_id
    if not drive_service:
        return None

    try:
        # Ищем существующую папку
        query = (
            f"name='{ROOT_FOLDER_NAME}' and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])

        if files:
            root_folder_id = files[0]["id"]
            logger.info(f"Корневая папка найдена: {root_folder_id}")
        else:
            # Создаём новую
            folder_meta = {
                "name": ROOT_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
            }
            folder = drive_service.files().create(body=folder_meta, fields="id").execute()
            root_folder_id = folder["id"]

            # Делаем доступной по ссылке (чтобы Егор мог открыть)
            drive_service.permissions().create(
                fileId=root_folder_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
            logger.info(f"Корневая папка создана: {root_folder_id}")

        return root_folder_id
    except Exception as e:
        logger.error(f"Ошибка работы с корневой папкой: {e}")
        return None


async def upload_files_to_drive(bot_instance, files_data: list, folder_name: str) -> str:
    """
    Загружает файлы заявки на Google Drive.
    Создаёт подпапку для каждой заявки.
    Возвращает ссылку на папку.
    """
    if not drive_service:
        return ""

    parent_id = get_or_create_root_folder()
    if not parent_id:
        return ""

    try:
        # Создаём подпапку для этой заявки
        subfolder_meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        subfolder = drive_service.files().create(
            body=subfolder_meta, fields="id,webViewLink"
        ).execute()
        subfolder_id = subfolder["id"]

        # Делаем папку доступной по ссылке
        drive_service.permissions().create(
            fileId=subfolder_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        folder_link = subfolder.get(
            "webViewLink",
            f"https://drive.google.com/drive/folders/{subfolder_id}"
        )

        # Загружаем каждый файл
        for f in files_data:
            try:
                tg_file = await bot_instance.get_file(f["file_id"])
                file_io = await bot_instance.download_file(tg_file.file_path)
                file_bytes = file_io.read()
                filename = f.get("file_name", "file")

                # Сохраняем во временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                file_meta = {
                    "name": filename,
                    "parents": [subfolder_id],
                }
                media = MediaFileUpload(tmp_path)
                drive_service.files().create(body=file_meta, media_body=media).execute()

                os.unlink(tmp_path)
                logger.info(f"Файл загружен на Drive: {filename}")

            except Exception as e:
                logger.error(f"Ошибка загрузки файла {f.get('file_name')}: {e}")

        return folder_link

    except Exception as e:
        logger.error(f"Ошибка загрузки на Drive: {e}")
        return ""


# ─── Бот ──────────────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ─── FSM ──────────────────────────────────────────────────────
class AppState(StatesGroup):
    waiting_company = State()
    waiting_order_name = State()
    waiting_phone = State()
    waiting_service = State()
    waiting_files = State()
    waiting_comment = State()
    waiting_deadline = State()


def get_service_keyboard():
    buttons = []
    for i, svc in enumerate(SERVICES):
        buttons.append([InlineKeyboardButton(text=svc, callback_data=f"svc_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── /start ───────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Фамилия/название компании")
    await state.set_state(AppState.waiting_company)


@router.message(Command("get_id"))
async def cmd_get_id(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
                         "Скопируйте его и вставьте в файл .env как MANAGER_TELEGRAM_ID",
                         parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Заявка отменена. Нажмите /start для новой.")


@router.message(Command("folder"))
async def cmd_folder(message: Message):
    """Показать ссылку на корневую папку со всеми заявками."""
    folder_id = get_or_create_root_folder()
    if folder_id:
        link = f"https://drive.google.com/drive/folders/{folder_id}"
        await message.answer(
            f"📁 Папка со всеми заявками:\n{link}",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Google Drive не подключён.")


# ─── Шаг 1: Компания ─────────────────────────────────────────
@router.message(AppState.waiting_company)
async def process_company(message: Message, state: FSMContext):
    await state.update_data(company=message.text.strip())
    await message.answer(
        "Ваш номер заказа/фамилия клиента\n"
        "(нужно чтобы потом сформировать общую отгрузку)"
    )
    await state.set_state(AppState.waiting_order_name)


# ─── Шаг 2: Заказ / клиент ───────────────────────────────────
@router.message(AppState.waiting_order_name)
async def process_order_name(message: Message, state: FSMContext):
    await state.update_data(order_name=message.text.strip())
    await message.answer("📞 Укажите ваш номер телефона для связи:")
    await state.set_state(AppState.waiting_phone)


# ─── Шаг 2.1: Телефон ────────────────────────────────────────
@router.message(AppState.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await message.answer("Что будем делать?", reply_markup=get_service_keyboard())
    await state.set_state(AppState.waiting_service)


# ─── Шаг 3: Услуга ───────────────────────────────────────────
@router.callback_query(AppState.waiting_service, F.data.startswith("svc_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    svc_index = int(callback.data.replace("svc_", ""))
    service = SERVICES[svc_index]
    await state.update_data(service=service)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Прикрепите 1-{MAX_FILES} файлов")
    await state.set_state(AppState.waiting_files)
    await callback.answer()


# ─── Шаг 4: Файлы ────────────────────────────────────────────
@router.message(AppState.waiting_files, F.photo)
async def process_file_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_FILES:
        await message.answer(f"⚠️ Максимум {MAX_FILES} файлов. Напишите «Конец отправки».")
        return
    photo = message.photo[-1]
    files.append({
        "type": "photo",
        "file_id": photo.file_id,
        "file_name": f"фото_{len(files) + 1}.jpg",
    })
    await state.update_data(files=files)


@router.message(AppState.waiting_files, F.document)
async def process_file_document(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_FILES:
        await message.answer(f"⚠️ Максимум {MAX_FILES} файлов. Напишите «Конец отправки».")
        return
    doc = message.document
    files.append({
        "type": "document",
        "file_id": doc.file_id,
        "file_name": doc.file_name or f"файл_{len(files) + 1}",
    })
    await state.update_data(files=files)


@router.message(AppState.waiting_files)
async def process_files_text(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    end_words = ("конец отправки", "конец", "стоп", "всё", "все", "готово", "далее", "дальше")
    if text in end_words:
        data = await state.get_data()
        files = data.get("files", [])
        if not files:
            await message.answer("⚠️ Вы не прикрепили файлов. Отправьте хотя бы один.")
            return
        await message.answer(
            "Комментарий (например: кромка другого цвета или что материал оплачен)"
        )
        await state.set_state(AppState.waiting_comment)
    else:
        await message.answer("Прикрепите файлы или напишите «Конец отправки».")


# ─── Шаг 5: Комментарий ──────────────────────────────────────
@router.message(AppState.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    await state.update_data(comment=message.text.strip())
    await message.answer("Планируемая дата готовности")
    await state.set_state(AppState.waiting_deadline)


# ─── Шаг 6: Дата → отправка ──────────────────────────────────
@router.message(AppState.waiting_deadline)
async def process_deadline(message: Message, state: FSMContext):
    await state.update_data(deadline=message.text.strip())
    data = await state.get_data()

    # Собираем все данные
    dt_now = datetime.now().strftime("%d.%m.%Y %H:%M")
    tg_user = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else message.from_user.full_name
    )
    company = data.get("company", "—")
    order_name = data.get("order_name", "—")
    phone = data.get("phone", "—")
    service = data.get("service", "—")
    comment = data.get("comment", "—")
    deadline = data.get("deadline", "—")
    files = data.get("files", [])

    status = await message.answer("⏳ Загружаю файлы и отправляю заявку...")

    if not MANAGER_TELEGRAM_ID:
        await status.edit_text("⚠️ Ошибка: В настройках не указан MANAGER_TELEGRAM_ID.")
        await state.clear()
        return

    # 1. Загружаем файлы на Google Drive
    drive_link = ""
    if files and drive_service:
        folder_name = f"{company}_{order_name}_{dt_now.replace(':', '-')}"
        drive_link = await upload_files_to_drive(bot, files, folder_name)
        if drive_link:
            logger.info(f"Файлы загружены на Drive: {drive_link}")
        else:
            logger.warning("Не удалось загрузить файлы на Drive")

    # 2. Отправляем в Telegram менеджеру
    try:
        text = (
            f"📋 <b>Новая заявка на раскрой</b>\n\n"
            f"🏢 <b>Компания:</b> {company}\n"
            f"👤 <b>Заказ:</b> {order_name}\n"
            f"📱 <b>Телефон:</b> {phone}\n"
            f"🛠 <b>Услуга:</b> {service}\n"
            f"💬 <b>Комментарий:</b> {comment}\n"
            f"📅 <b>Дата готовности:</b> {deadline}\n"
            f"🔗 <b>Telegram:</b> {tg_user}\n"
            f"⏱ <b>Время:</b> {dt_now}"
        )
        if drive_link:
            text += f"\n📁 <b>Файлы на Диске:</b> {drive_link}"

        await bot.send_message(MANAGER_TELEGRAM_ID, text, parse_mode="HTML")

        # Пересылаем файлы напрямую тоже
        if files:
            media_group = []
            for f in files:
                file_id = f["file_id"]
                if f["type"] == "photo":
                    media_group.append(InputMediaPhoto(media=file_id))
                else:
                    media_group.append(InputMediaDocument(media=file_id))
            if media_group:
                await bot.send_media_group(MANAGER_TELEGRAM_ID, media=media_group)

    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        await status.edit_text("⚠️ Ошибка пересылки в Telegram.")
        await state.clear()
        return

    # 3. Пишем в Google Таблицу
    if worksheet:
        try:
            row = [
                tg_user,                                 # 1. Telegram
                dt_now,                                  # 2. Время
                f"{company} / {order_name}",             # 3. Фамилия
                phone,                                   # 4. Телефон
                service,                                 # 5. Услуга
                drive_link or "Файлы в Telegram",        # 6. Ссылка на диск
                comment,                                 # 7. Комментарий
                deadline                                 # 8. Дата
            ]
            worksheet.append_row(row)
            await status.edit_text("Ваша заявка успешно отправлена ✅")
        except Exception as e:
            logger.error(f"Google Sheets append error: {e}")
            await status.edit_text("Заявка отправлена ✅, но не записалась в Таблицу.")
    else:
        await status.edit_text("Заявка отправлена в Telegram ✅ (Таблица не подключена)")

    await state.clear()


# ─── Запуск ───────────────────────────────────────────────────
async def main():
    logger.info("Бот заявок запущен")
    # При старте создаём/находим корневую папку
    folder_id = get_or_create_root_folder()
    if folder_id:
        logger.info(f"Корневая папка Drive: https://drive.google.com/drive/folders/{folder_id}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
