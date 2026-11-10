# Task Management API

REST API для системи управління задачами: задачі з жорсткою схемою переходів між статусами,
призначення виконавців, коментарі, пошук / фільтрація / сортування з пагінацією,
службові endpoints (прострочені задачі, статистика) та фонова задача, яка автоматично
скасовує задачі, що не були завершені до дедлайну.

## Стек

Фреймворк: FastAPI |
ORM: SQLAlchemy 2.0 (async, драйвер asyncpg) |
БД: PostgreSQL 16 |
Міграції: Alembic (async env) |
Валідація: Pydantic v2, pydantic-settings |
Автентифікація: JWT (PyJWT), паролі хешуються Argon2 (pwdlib) |
Фонові задачі: asyncio-воркер у lifespan + FastAPI `BackgroundTasks` 
Тести: pytest, pytest-asyncio, httpx 
Запуск: Docker Compose 

## Швидкий старт

Потрібні лише Docker та Docker Compose.

```bash
docker compose up --build
```

Міграції застосовуються автоматично під час старту контейнера `api`.

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health-check: http://localhost:8000/health

Параметри (порт, секрет JWT, облікові дані БД тощо) можна змінити через змінні оточення
або файл `.env` — приклад у `.env.example`. Значення за замовчуванням підходять для локальної
розробки (у лозі при цьому з'являється попередження про тестовий `SECRET_KEY`).

Для production задайте `ENVIRONMENT=production` і власний `SECRET_KEY`: у цьому режимі застосунок
**відмовляється стартувати** з прикладом-заглушкою. Згенерувати секрет можна так:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

### Тести

```bash
docker compose run --rm tests
```

Тести працюють з окремою базою `<назва_бази>_test`, яка створюється автоматично, а схема
перестворюється перед кожним тестом. Дані основної бази не зачіпаються.

### Запуск без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # вкажіть DATABASE_URL на вашу PostgreSQL
alembic upgrade head
uvicorn app.main:app --reload
pytest
```


### Параметри `GET /tasks`

| Параметр | Опис |
| --- | --- |
| `search` | Пошук за назвою та описом, без урахування регістру. Спецсимволи `%` і `_` екрануються |
| `status` | Фільтр за статусом; параметр можна повторювати: `status=backlog&status=review` |
| `priority` | Фільтр за пріоритетом; можна повторювати |
| `assignee_id` | Фільтр за виконавцем |
| `deadline_from`, `deadline_to` | Діапазон дедлайну (включно), ISO 8601 |
| `sort` | Поля через кому: `created_at`, `deadline`, `priority`; префікс `-` означає спадання. За замовчуванням `-priority,deadline` (High → Medium → Low, далі найближчий дедлайн) |
| `page`, `page_size` | Пагінація (`page` до 1 000 000, `page_size` до 100, за замовчуванням 20) |

Відповідь списку: `{"items": [...], "total": 42, "page": 1, "page_size": 20, "pages": 3}`.

### Права доступу

Специфікація не описує ролі, тому застосовано мінімальну розумну модель:

- читати задачі та коментарі, створювати задачі й коментувати може будь-який автентифікований користувач;
- редагувати та видаляти задачу може тільки її автор;
- змінювати статус може автор або виконавець.

## Фонова задача

`OverdueTaskWorker` (`app/workers/overdue.py`) запускається у `lifespan` застосунку й раз на
`OVERDUE_CHECK_INTERVAL_SECONDS` (за замовчуванням 60) виконує один `UPDATE ... RETURNING`,
який переводить у `cancelled` усі задачі зі статусами `backlog` / `in_progress` / `review`
та дедлайном у минулому. Це безпечно за кількох реплік: операція атомарна й ідемпотентна,
одна задача не може бути скасована двічі. Збій окремого проходу (наприклад, перезапуск БД)
логується й не зупиняє цикл. Воркер вимикається змінною `OVERDUE_WORKER_ENABLED=false`.

Окремо використано FastAPI `BackgroundTasks`: після успішного призначення виконавця
викликається `notify_assignee` (`app/services/notifications.py`). Зараз це лише лог-запис,
але точка розширення для e-mail чи webhook уже на місці.


