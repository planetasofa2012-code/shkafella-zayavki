# Тест: кто владелец папки + попытка загрузить маленький файл
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile, os

SCOPES = ["https://www.googleapis.com/auth/drive"]
creds = service_account.Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
drive = build("drive", "v3", credentials=creds)

# 1. Находим корневую папку "Заявки Шкафелла"
results = drive.files().list(
    q="name='Заявки_Шкафелла_Бот' and mimeType='application/vnd.google-apps.folder' and trashed=false",
    fields="files(id,name,owners,sharingUser,capabilities)"
).execute()

files = results.get("files", [])
if files:
    folder = files[0]
    print(f"=== Папка: {folder['name']} ===")
    print(f"ID: {folder['id']}")
    owners = folder.get("owners", [])
    for o in owners:
        print(f"Владелец: {o.get('displayName')} ({o.get('emailAddress')})")
    print(f"Capabilities: {folder.get('capabilities', {})}")
else:
    print("Папка не найдена!")
    exit()

# 2. Считаем реальный размер ФАЙЛОВ (не папок) внутри
print("\n=== Считаем размер файлов ===")
all_files = []
page_token = None
while True:
    resp = drive.files().list(
        q="mimeType!='application/vnd.google-apps.folder' and trashed=false",
        fields="nextPageToken, files(id,name,size)",
        pageSize=100,
        pageToken=page_token
    ).execute()
    all_files.extend(resp.get("files", []))
    page_token = resp.get("nextPageToken")
    if not page_token:
        break

total_bytes = sum(int(f.get("size", 0)) for f in all_files)
print(f"Всего файлов (не папок): {len(all_files)}")
print(f"Общий размер: {total_bytes / 1024**2:.1f} МБ ({total_bytes / 1024**3:.2f} ГБ)")

# 3. Пробуем загрузить тестовый файл
print("\n=== Тест загрузки ===")
try:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w") as f:
        f.write("test upload")
        tmp = f.name

    meta = {"name": "TEST_DELETE_ME.txt", "parents": [folder["id"]]}
    media = MediaFileUpload(tmp, mimetype="text/plain")
    result = drive.files().create(body=meta, media_body=media, fields="id").execute()
    print(f"УСПЕХ! Файл загружен: {result['id']}")

    # Удаляем тестовый файл
    drive.files().delete(fileId=result["id"]).execute()
    print("Тестовый файл удалён.")
    os.unlink(tmp)
except Exception as e:
    print(f"ОШИБКА: {e}")
    os.unlink(tmp)
