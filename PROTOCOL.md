# PROTOCOL.md — Бот заявок «Шкафелла»

> Проект: Telegram-бот приёма заявок на мебельный раскрой
> Репозиторий: https://github.com/planetasofa2012-code/shkafella-zayavki
> Сервер: `5.42.104.62` (Timeweb VPS, `/opt/shkafella-zayavki`)

---

## Текущий фокус

✅ **Проект в продакшне.** Бот работает 24/7 на сервере. Все заявки записываются в Google Таблицу и на Google Drive.

---

## Хронология работы

### 2026-03-31 — Перевод на OAuth авторизацию и доработка логики

| Время | Задача | Результат |
|-------|--------|-----------|
| 17:00 | Рефакторинг столбцов в Google Таблице | ✅ Компания и Фамилия разделены. Ошибка со ссылками на картинки исправлена. |
| 17:33 | Внедрение OAuth (`google-auth-oauthlib`) | ✅ Вместо сервисного аккаунта используется реальный Google аккаунт для обхода лимита 15ГБ. `token.json` сгенерен успешно. |
| 17:46 | Изменение логики загрузки GDrive | ✅ В таблицу пишется одна короткая ссылка на всю папку заявки, как просил клиент. |
| 18:50 | Подготовка к деплою в Docker | ✅ В `docker-compose.yml` проброшен `token.json`, обновлён `requirements.txt`. |

### 2026-03-27 — Ранее: Деплой и финализация

| Время | Задача | Результат |
|-------|--------|-----------|
| 15:30 | Создание `credentials.json` на сервере через nano | Файл оказался пуст (0 байт) |
| 15:58 | Пересоздание через `cat > ... << 'ENDOFFILE'` | ✅ Файл валидный (JSON OK) |
| 16:02 | Перезапуск контейнера `docker-compose restart` | ✅ Google Sheets подключён, Google Drive подключён |
| 16:13 | Тест заявки — полный цикл | ✅ «Ваша заявка успешно отправлена» |
| 16:21 | Отключение Telegram-уведомлений менеджеру | ✅ Заявки только в таблицу + Drive |
| 16:24 | Добавление кнопки «Далее ➡️» после файлов | ✅ Задеплоено |
| 16:26 | Деплой обновлений на сервер | ✅ `git pull && docker-compose up -d --build` |

### Ранее — Разработка и первый деплой

| Задача | Результат |
|--------|-----------|
| Создание бота на aiogram 3.x с FSM | ✅ 7 шагов: компания → заказ → телефон → услуга → файлы → комментарий → дедлайн |
| Интеграция Google Sheets (gspread) | ✅ Запись строки в таблицу `1ovh6v9mNXUTBtJlyNbf3e6a1XoP_9jd4Qxe48KFlZCg` |
| Интеграция Google Drive API | ✅ Автоматическая загрузка файлов в подпапку + публичная ссылка |
| Docker + docker-compose | ✅ Контейнер с `restart: always` |
| GitHub CI/CD | ✅ `git push → git pull на сервере → docker-compose rebuild` |

---

## Архитектура

```
Клиент (Telegram) → Бот (aiogram 3.x) → Google Sheets + Google Drive
                                        → Telegram менеджеру (опционально)
```

### Файловая структура
```
shkafella-zayavki/
├── bot.py              # Основная логика бота (FSM + Google API)
├── config.py           # Конфигурация из .env
├── requirements.txt    # Зависимости Python
├── Dockerfile          # Сборка контейнера
├── docker-compose.yml  # Оркестрация (проброшен token.json)
├── .env                # BOT_TOKEN, MANAGER_TELEGRAM_ID (не в git!)
├── client_secret.json  # Конфиг Oauth клиента Google (не в git!)
├── token.json          # Токен доступа Google API (не в git!)
├── .gitignore
└── README.md
```

---

## Конфигурация

### .env (на сервере: `/opt/shkafella-zayavki/.env`)
```
BOT_TOKEN=токен_бота
MANAGER_TELEGRAM_ID=        # пусто = уведомления отключены
```

### credentials.json
- Сервис-аккаунт: `shkafella-bot@shkafella-bot.iam.gserviceaccount.com`
- Google Sheet ID: `1ovh6v9mNXUTBtJlyNbf3e6a1XoP_9jd4Qxe48KFlZCg`
- Корневая папка Drive: `Заявки_Шкафелла_Бот`

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начать новую заявку |
| `/cancel` | Отменить текущую заявку |
| `/get_id` | Показать свой Telegram ID |
| `/folder` | Ссылка на корневую папку Drive |

---

## Управление сервером

### Проверить статус
```bash
cd /opt/shkafella-zayavki
docker-compose ps
```

### Просмотр логов
```bash
docker logs shkafella-zayavki_bot_1 --tail=20
```

### Перезапуск
```bash
docker-compose restart
```

### Обновление кода
```bash
git pull && docker-compose down && docker-compose up -d --build
```

### Включить Telegram-уведомления
```bash
nano .env
# Установить MANAGER_TELEGRAM_ID=123456789
docker-compose restart
```

---

## Полезные находки

| Находка | Описание |
|---------|----------|
| `nano` в Timeweb | Через веб-консоль Timeweb вставка в nano ненадёжна — файл сохраняется пустым. Лучше использовать `cat > file << 'EOF'` |
| Docker volume + OAuth токен | `token.json` монтируется через volume *без fлага :ro*, так как токен обновляется. При изменении на хосте нужен `restart`. |
| Публичный репо | Для простоты деплоя репо сделан публичным — `git pull` на сервере работает без токена |

---

## Что передать Егору

1. **Ссылка на бота** — `t.me/имя_бота`
2. **Ссылка на Google Таблицу** — доступ уже расшарен
3. **Ссылка на Drive папку** — команда `/folder` в боте
4. Уведомления в TG отключены — заявки только в таблицу

---

*Последнее обновление: 2026-03-27 17:02*
