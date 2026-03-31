# Скрипт проверки квоты Google Drive сервис-аккаунта
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

creds = service_account.Credentials.from_service_account_file(
    "credentials.json", scopes=SCOPES
)
drive = build("drive", "v3", credentials=creds)

# 1. Квота диска
about = drive.about().get(fields="storageQuota, user").execute()
quota = about.get("storageQuota", {})
user = about.get("user", {})

print(f"=== Google Drive: {user.get('emailAddress', '?')} ===")
print(f"Лимит:      {int(quota.get('limit', 0)) / 1024**3:.2f} ГБ")
print(f"Использовано: {int(quota.get('usage', 0)) / 1024**3:.2f} ГБ")
print(f"В корзине:   {int(quota.get('usageInDriveTrash', 0)) / 1024**3:.2f} ГБ")
print()

# 2. Топ-20 самых тяжёлых файлов
print("=== Топ-20 файлов по размеру ===")
results = drive.files().list(
    pageSize=100,
    fields="files(id,name,size,mimeType,createdTime)",
    orderBy="quotaBytesUsed desc",
    q="trashed=false"
).execute()

files = results.get("files", [])
total = 0
for i, f in enumerate(files[:20]):
    size = int(f.get("size", 0))
    total += size
    mb = size / 1024**2
    print(f"  {i+1:2}. {mb:8.2f} МБ  {f.get('createdTime', '?')[:10]}  {f['name'][:50]}")

print(f"\nВсего файлов на диске: {len(files)}+")
print(f"Суммарно топ-20: {total / 1024**3:.2f} ГБ")
