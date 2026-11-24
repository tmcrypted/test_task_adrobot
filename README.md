# Adrobot — Keitaro wrapper

Локальная обёртка над Admin API тестового Keitaro: создание кампаний, маршрутизация по GEO и редактор офферов в потоках.

## Запуск через Docker

Требования: Docker Desktop (Windows/macOS) или Docker Engine + Docker Compose plugin (Linux).

1. В корне проекта создайте локальный файл настроек:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Откройте `.env`, вставьте свой `API_KEY` со страницы тестового стенда и замените `CAMPAIGN_PREFIX` на `test_<фамилия>_`.
3. Запустите из корня проекта:

   ```powershell
   docker compose up --build
   ```

Дождитесь статуса `healthy` у сервиса `db` и `Up` у `app`, затем откройте <http://localhost:8000>. Документация FastAPI доступна на <http://localhost:8000/docs>.

React собирается внутри Docker-образа, FastAPI отдаёт собранный интерфейс. PostgreSQL хранит локальные черновики, архив связей офферов и историю операций. Данные сохраняются в томе `postgres_data`.

Остановить контейнеры: `Ctrl+C`. Удалить контейнеры: `docker compose down`. Для полного сброса локальной базы и всех её данных: `docker compose down -v`.

## Запуск без Docker

Docker не обязателен. Для локального запуска понадобятся Python 3.12+, Node.js 22+ и npm. В этом режиме приложение использует SQLite; отдельный сервер PostgreSQL не нужен.

Сначала один раз создайте `.env` и укажите в нём свой `API_KEY` со страницы тестового стенда и префикс `CAMPAIGN_PREFIX` (например, `test_ivanov_`):

```powershell
Copy-Item .env.example .env
```

Далее из корня проекта выполните в PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build

$env:PYTHONPATH = "$PWD\backend"
$env:DATABASE_URL = "sqlite:///./adrobot.db"
$env:FRONTEND_DIST = "$PWD\frontend\dist"
python -m alembic -c backend\alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

На macOS/Linux из корня проекта выполните:

```bash
cp .env.example .env # один раз; затем укажите в .env свой API_KEY и CAMPAIGN_PREFIX
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend

export PYTHONPATH="$PWD/backend"
export DATABASE_URL="sqlite:///./adrobot.db"
export FRONTEND_DIST="$PWD/frontend/dist"
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Откройте <http://localhost:8000>. Backend раздаёт собранный React-интерфейс и API с одного адреса. `npm run dev` сам по себе не проксирует запросы к API.

## Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `API_KEY` | Ключ Admin API стенда. Передаётся только backend в HTTP-заголовке `Api-Key`. |
| `KEITARO_BASE_URL` | Адрес Admin API; по умолчанию тестовый стенд. |
| `CAMPAIGN_PREFIX` | Префикс имени кампании, например `test_ivanov_`. |
| `POSTGRES_PASSWORD` | Пароль локального контейнера PostgreSQL. |

Не добавляйте `.env` в Git и не вставляйте API-ключ в исходники или запросы frontend. В репозитории хранится только `.env.example` с placeholder-значением.

## Потоки и офферы

- Поток 1 создан первым: выбранная страна (`country`, `accept`) направляется на `https://google.com`.
- Поток 2 не имеет GEO-фильтра и отправляет остальной трафик на выбранный оффер.
- В редакторе `Fetch Streams` синхронизирует состояние с Keitaro. Добавление, удаление и возврат оффера формируют локальный черновик.
- `Push to Keitaro` публикует полный актуальный массив `offers`; `Cancel` отменяет неопубликованные локальные изменения.
- Удалённые из потока офферы остаются в локальном архиве со статусом `removed` и долей `0%`. `Bring back` возвращает существующий в каталоге Keitaro оффер в черновик.
- Доли целочисленные, активные офферы вместе дают `100%`. Pin закрепляет текущую долю. В потоке должен оставаться хотя бы один активный незакреплённый оффер.

Каталоги доменов, групп, источников и офферов на тестовом стенде доступны только для чтения. Стенд не предоставляет клики и статистику.

## Миграции

При запуске через Docker миграции выполняются автоматически командой `alembic upgrade head`. При локальном запуске без Docker выполните команду из корня проекта, указанную в инструкции выше, после установки зависимостей и настройки переменных окружения.

`DATABASE_URL` по умолчанию указывает на SQLite. Чтобы использовать локальный PostgreSQL без Docker, установите PostgreSQL и задайте `DATABASE_URL` в формате `postgresql+psycopg://user:password@localhost:5432/adrobot`.

## Тесты и сборка frontend

```bash
cd backend
python -m pytest

cd ../frontend
npm install
npm test
npm run build
```

Backend-тесты используют fake Keitaro client, поэтому не создают записи на стенде. Live smoke-проверку выполняйте вручную после настройки `.env`; каждый вызов виден в журнале тестового API.
