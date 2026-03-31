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
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import BOT_TOKEN, SERVICES, MAX_FILES



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

# ID расшаренной папки на Google Диске (владелец — Егор или тестовый аккаунт)
# Сервис-аккаунт должен иметь роль «Редактор» в этой папке
SHARED_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

worksheet = None
drive_service = None

try:
    credentials = None
    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file("token.json", SCOPES)
        
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        elif os.path.exists("client_secret.json"):
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            credentials = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(credentials.to_json())
        else:
            logger.warning("Нет файла client_secret.json или token.json")

    if credentials:
        # Google Sheets
        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.sheet1
        logger.info("Google Sheets подключён!")

        # Google Drive
        drive_service = build("drive", "v3", credentials=credentials)
        if SHARED_FOLDER_ID:
            logger.info(f"Google Drive подключён! Папка: {SHARED_FOLDER_ID}")
        else:
            logger.warning("GOOGLE_DRIVE_FOLDER_ID не задан в .env — загрузка файлов отключена")
except Exception as e:
    logger.error(f"Ошибка подключения к Google API: {e}")


async def upload_files_to_drive(bot_instance, files_data: list, folder_name: str) -> tuple[str, list]:
    """
    Загружает файлы заявки на Google Drive в расшаренную папку.
    Создаёт подпапку для каждой заявки.
    Возвращает (id_папки, список_файлов: [{"id": ..., "name": ..., "type": ...}, ...])
    """
    if not drive_service or not SHARED_FOLDER_ID:
        logger.warning("Drive не настроен — файлы не загружены")
        return "", []

    try:
        # Создаём подпапку для этой заявки внутри расшаренной папки
        subfolder_meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [SHARED_FOLDER_ID],
        }
        subfolder = drive_service.files().create(
            body=subfolder_meta, fields="id"
        ).execute()
        subfolder_id = subfolder["id"]

        uploaded_files = []

        # Загружаем каждый файл
        for f in files_data:
            try:
                tg_file = await bot_instance.get_file(f["file_id"])
                file_io = await bot_instance.download_file(tg_file.file_path)
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
                uploaded = drive_service.files().create(
                    body=file_meta, media_body=media, fields="id"
                ).execute()

                uploaded_files.append({
                    "id": uploaded["id"],
                    "name": filename,
                    "type": f["type"],
                })

                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                logger.info(f"Файл загружен на Drive: {filename}")

            except Exception as e:
                logger.error(f"Ошибка загрузки файла {f.get('file_name')}: {e}")

        return subfolder_id, uploaded_files

    except Exception as e:
        logger.error(f"Ошибка загрузки на Drive: {e}")
        return "", []


# ─── Бот ──────────────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ─── FSM ──────────────────────────────────────────────────────
class AppState(StatesGroup):
    waiting_company = State()
    waiting_order_name = State()
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
    if SHARED_FOLDER_ID:
        link = f"https://drive.google.com/drive/folders/{SHARED_FOLDER_ID}"
        await message.answer(
            f"📁 Папка со всеми заявками:\n{link}",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Google Drive не подключён. Задайте GOOGLE_DRIVE_FOLDER_ID в .env")


# ─── Шаг 1: Компания ─────────────────────────────────────────
@router.message(AppState.waiting_company)
async def process_company(message: Message, state: FSMContext):
    await state.update_data(company=message.text.strip())
    await message.answer(
        "Ваш номер заказа/фамилия клиента\n"
        "(нужно чтобы потом сформировать общую отгрузку)"
    )
    await state.set_state(AppState.waiting_order_name)


# ─── Шаг 2: Заказ / клиент ───────────────────────────────
@router.message(AppState.waiting_order_name)
async def process_order_name(message: Message, state: FSMContext):
    await state.update_data(order_name=message.text.strip())
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


def get_files_done_keyboard(count: int):
    """Кнопка «Далее» после прикрепления файлов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Далее ➡️ ({count} файл.)", callback_data="files_done")]
    ])


# ─── Шаг 4: Файлы ────────────────────────────────────────────
@router.message(AppState.waiting_files, F.photo)
async def process_file_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_FILES:
        await message.answer(f"⚠️ Максимум {MAX_FILES} файлов.", reply_markup=get_files_done_keyboard(len(files)))
        return
    photo = message.photo[-1]
    files.append({
        "type": "photo",
        "file_id": photo.file_id,
        "file_name": f"фото_{len(files) + 1}.jpg",
    })
    await state.update_data(files=files)
    await message.answer(
        f"✅ Файл {len(files)} принят. Отправьте ещё или нажмите кнопку.",
        reply_markup=get_files_done_keyboard(len(files))
    )


@router.message(AppState.waiting_files, F.document)
async def process_file_document(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_FILES:
        await message.answer(f"⚠️ Максимум {MAX_FILES} файлов.", reply_markup=get_files_done_keyboard(len(files)))
        return
    doc = message.document
    files.append({
        "type": "document",
        "file_id": doc.file_id,
        "file_name": doc.file_name or f"файл_{len(files) + 1}",
    })
    await state.update_data(files=files)
    await message.answer(
        f"✅ Файл {len(files)} принят. Отправьте ещё или нажмите кнопку.",
        reply_markup=get_files_done_keyboard(len(files))
    )


@router.callback_query(AppState.waiting_files, F.data == "files_done")
async def process_files_done_button(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if not files:
        await callback.answer("⚠️ Сначала прикрепите хотя бы один файл.")
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Комментарий (например клей PUR)"
    )
    await state.set_state(AppState.waiting_comment)
    await callback.answer()


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
            "Комментарий (например клей PUR)"
        )
        await state.set_state(AppState.waiting_comment)
    else:
        await message.answer("Прикрепите файлы или напишите «Далее».")


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
    service = data.get("service", "—")
    comment = data.get("comment", "—")
    deadline = data.get("deadline", "—")
    files = data.get("files", [])

    status = await message.answer("⏳ Загружаю файлы и отправляю заявку...")

    # 1. Загружаем файлы на Google Drive
    folder_id = ""
    uploaded_files = []
    if files and drive_service:
        folder_name = f"{company}_{order_name}_{dt_now.replace(':', '-')}"
        folder_id, uploaded_files = await upload_files_to_drive(bot, files, folder_name)
        if uploaded_files:
            logger.info(f"Загружено файлов на Drive: {len(uploaded_files)}")
        else:
            logger.warning("Не удалось загрузить файлы на Drive")

    # 2. Пишем в Google Таблицу
    if worksheet:
        try:
            folder_link = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else "Нет файлов"

            row = [
                tg_user,           # A. Telegram
                dt_now,            # B. Время
                company,           # C. Название/Фамилия
                order_name,        # D. Заказ/Телефон
                service,           # E. Услуга
                folder_link,       # F. Ссылка на саму папку с файлами
                comment,           # G. Комментарий
                deadline,          # H. Дата готовности
            ]

            worksheet.append_row(row, value_input_option="USER_ENTERED")
            await status.edit_text("Ваша заявка отправлена ✅")
        except Exception as e:
            logger.error(f"Google Sheets append error: {e}")
            await status.edit_text("Заявка отправлена ✅, но не записалась в Таблицу.")
    else:
        await status.edit_text("⚠️ Таблица не подключена. Заявка не записана.")

    await state.clear()


# ─── Запуск ───────────────────────────────────────────────────
async def main():
    logger.info("Бот заявок запущен")
    if SHARED_FOLDER_ID:
        logger.info(f"Папка Drive: https://drive.google.com/drive/folders/{SHARED_FOLDER_ID}")
    else:
        logger.warning("GOOGLE_DRIVE_FOLDER_ID не задан — файлы не будут загружаться")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
