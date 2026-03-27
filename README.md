# Shkafella Zayavki Bot

Telegram бот для приёма заявок на мебельный раскрой.

## Возможности
- Сбор заявки по шагам (компания, заказ, телефон, услуга, файлы, комментарий, дата)
- Загрузка файлов на Google Drive (ссылка в таблицу)
- Пересылка заявки и файлов менеджеру в Telegram
- Запись строки в Google Таблицу

## Установка

### 1. Клонировать
```bash
git clone https://github.com/planetasofa2012-code/shkafella-zayavki.git
cd shkafella-zayavki
```

### 2. Настроить
```bash
cp .env.example .env
# Заполнить BOT_TOKEN и MANAGER_TELEGRAM_ID
```

Положить `credentials.json` (ключ сервис-аккаунта Google) в корень проекта.

### 3. Запустить (Docker)
```bash
docker-compose up -d --build
```

### 4. Команды бота
- `/start` — начать заявку
- `/cancel` — отменить заявку
- `/folder` — ссылка на папку с файлами заявок
- `/get_id` — узнать свой Telegram ID
