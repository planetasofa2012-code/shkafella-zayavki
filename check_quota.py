"""Показать квоту Google Drive сервис-аккаунта — доказательство переполнения."""
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=["https://www.googleapis.com/auth/drive"]
)
drive = build("drive", "v3", credentials=creds)

# Квота диска
about = drive.about().get(fields="storageQuota,user").execute()
q = about["storageQuota"]
user = about["user"]

limit = int(q.get("limit", 0))
usage = int(q.get("usage", 0))

print("=" * 50)
print(f"Аккаунт: {user['emailAddress']}")
print(f"Лимит:   {limit / 1e9:.2f} ГБ")
print(f"Занято:  {usage / 1e9:.2f} ГБ")
print(f"Свободно: {(limit - usage) / 1e9:.2f} ГБ" if limit > 0 else "Свободно: 0 (лимит = 0!)")
print("=" * 50)

if limit == 0:
    print("\n⛔ ДОКАЗАТЕЛЬСТВО: лимит = 0 байт.")
    print("Google НЕ выделяет хранилище сервис-аккаунтам.")
    print("Любая загрузка файла даст ошибку storageQuotaExceeded.")
elif usage >= limit:
    print(f"\n⛔ Диск ПОЛОН: {usage / 1e9:.2f} из {limit / 1e9:.2f} ГБ")
else:
    print(f"\n✅ Есть место: {(limit - usage) / 1e9:.2f} ГБ свободно")
