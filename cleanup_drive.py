"""
Скрипт очистки Google Drive сервис-аккаунта.
Удаляет ВСЕ файлы и папки, чтобы освободить квоту.
"""
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]

credentials = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
drive = build("drive", "v3", credentials=credentials)


def list_all_files():
    """Получить все файлы на Диске сервис-аккаунта."""
    all_files = []
    page_token = None
    while True:
        response = drive.files().list(
            q="trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100,
            pageToken=page_token
        ).execute()
        files = response.get("files", [])
        all_files.extend(files)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return all_files


def main():
    # Показываем что есть
    files = list_all_files()
    if not files:
        print("Диск сервис-аккаунта уже пуст!")
        return

    total_size = 0
    print(f"\nНайдено файлов/папок: {len(files)}\n")
    for f in files:
        size = int(f.get("size", 0))
        total_size += size
        size_mb = size / 1024 / 1024
        print(f"  {f['name']:<50} {size_mb:>8.2f} МБ  ({f['mimeType'][:30]})")

    print(f"\n{'='*70}")
    print(f"ИТОГО: {total_size / 1024 / 1024:.2f} МБ ({total_size / 1024 / 1024 / 1024:.2f} ГБ)")
    print(f"{'='*70}")

    # Подтверждение
    answer = input(f"\nУдалить ВСЕ {len(files)} файлов? (да/нет): ").strip().lower()
    if answer != "да":
        print("Отменено.")
        return

    # Удаляем
    deleted = 0
    errors = 0
    for f in files:
        try:
            drive.files().delete(fileId=f["id"]).execute()
            deleted += 1
            print(f"  ✓ Удалён: {f['name']}")
        except Exception as e:
            errors += 1
            print(f"  ✗ Ошибка ({f['name']}): {e}")

    # Проверяем также корзину
    print("\nОчищаем корзину...")
    try:
        drive.files().emptyTrash().execute()
        print("  ✓ Корзина очищена")
    except Exception as e:
        print(f"  ✗ Ошибка очистки корзины: {e}")

    print(f"\n{'='*70}")
    print(f"Удалено: {deleted}, Ошибок: {errors}")
    print(f"{'='*70}")

    # Проверяем квоту после очистки
    about = drive.about().get(fields="storageQuota").execute()
    quota = about.get("storageQuota", {})
    used = int(quota.get("usage", 0))
    limit = int(quota.get("limit", 0))
    print(f"\nКвота после очистки: {used / 1024 / 1024:.2f} МБ / {limit / 1024 / 1024 / 1024:.2f} ГБ")


if __name__ == "__main__":
    main()
