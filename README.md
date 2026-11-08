# «Баланс» — трекер состояния и нагрузки

Веб-приложение (mobile-first) по техническому заданию из файла `ТЗ.docx`:
ежедневная отметка настроения и стресса → рекомендация по количеству задач →
графики динамики состояния и выполнения.

## Стек (согласовано)

| Слой | Технология | Комментарий |
|---|---|---|
| Backend | Python 3.12 + FastAPI | REST API и вся бизнес-логика на сервере |
| ORM / БД | SQLAlchemy 2.x, **SQLite** | Код готов к PostgreSQL: задайте `BALANS_DATABASE_URL` |
| Аутентификация | JWT (access) в httpOnly-cookie, bcrypt | Изоляция данных по `user_id` |
| Валидация | Pydantic v2 | Шкалы 1–5 / 1–10, заметка ≤ 500, теги, даты |
| Frontend | **Jinja2 + ванильный JS/CSS** | Без сборки и Node; графики — собственный SVG |
| Тесты | pytest + httpx (TestClient) | 43 теста, покрытие критериев приёмки AC-1…AC-23 |

Решения из раздела 12 ТЗ: frontend — Jinja2 (вместо React, Node не требуется),
БД — SQLite с лёгким переключением на PostgreSQL, категории задач — предустановленные.

## Запуск

```bash
pip install -r requirements.txt

# (необязательно) демо-данные для графиков:
python -m app.seed          # вход: demo@demo.ru / demo1234

# запуск:
python run.py               # или: python -m uvicorn app.main:app --reload
```

Открыть <http://127.0.0.1:8000>.

### Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BALANS_DATABASE_URL` | `sqlite:///balans.db` | напр. `postgresql+psycopg2://user:pass@host/balans` |
| `BALANS_SECRET_KEY` | dev-значение | **обязательна для продакшена** (подпись JWT) |
| `BALANS_TOKEN_TTL_MINUTES` | `720` | время жизни access-токена |
| `BALANS_COOKIE_SECURE` | `0` | `1` на HTTPS |

### PostgreSQL

```bash
pip install psycopg2-binary
set BALANS_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/balans
python run.py
```

Схема создаётся автоматически (`create_all`); для продакшена можно добавить Alembic.

## Тесты

```bash
python -m pytest
```

Тесты разложены по файлам: аккаунт и изоляция (`test_auth`), записи и границы дат
(`test_mood`), задачи (`test_tasks`), все ветки рекомендации (`test_recommendation`),
аналитика/дайджест/темы (`test_analytics`).

## Структура

```
app/
  main.py            # фабрика приложения, маршруты, шаблоны, статика
  models.py          # User, MoodEntry, Task + фиксированные теги/категории
  schemas.py         # Pydantic-схемы API
  security.py        # bcrypt + JWT
  dates.py           # «сегодня» по поясу пользователя, правила 7/3 дней
  deps.py            # текущий пользователь, rate limiting
  routers/           # auth_api, me, mood, tasks, insights (JSON) + pages (Jinja2)
  services/
    recommendation.py  # расчёт рекомендации (п.6.1–6.2 ТЗ), чистые функции
    analytics.py       # данные графиков и дайджест (п.6.3)
  templates/         # base, auth, today, history, tasks, analytics, settings
  static/            # app.css (темы), app.js, charts.js (SVG), analytics.js
tests/               # pytest, критерии приёмки AC-1…AC-22
```

## Соответствие ТЗ (кратко)

- **FR-1…FR-4** — регистрация/вход, JWT-cookie, изоляция по `user_id`, часовой пояс.
- **FR-5…FR-12** — записи со шкалами, тегами, upsert «одна запись на дату»,
  ограничения создание ≤ 7 дней / редактирование ≤ 3 дня — **на бэкенде**.
- **FR-13…FR-19** — задачи: CRUD, статусы `planned/done/cancelled`, дедлайны,
  приоритеты, категории, фильтры; статистика по `planned_date`.
- **FR-20…FR-26** — рекомендация `recommendation_service` с объяснением,
  личным лимитом, мягкой подсказкой при перегрузке и дисклеймером;
  без отметки — карточка «Состояние не отмечено» (п.6.2).
- **FR-27…FR-29** — in-app баннер «Отметьте состояние», скрывается после сохранения.
- **FR-30…FR-37** — два графика (настроение + столбцы выполненных; стресс отдельно),
  периоды 7/30/90, tooltip, фильтр по тегам, пустое состояние (< 3 дней), дайджест с трендом.
- **FR-38…FR-41** — настройки: комфортное число задач, тема (сохраняется),
  часовой пояс, выход.

## Доступность и браузеры

Контрастные темы на CSS-переменных, подписи у всех полей, клавиатурная
навигация (Tab/стрелки на графиках, Esc — закрыть подсказку), `aria-*`,
mobile-first-вёрстка; проверено в Chrome, Firefox, Safari-совместимом рендере.

## Дизайн-допущения

- Тон — поддерживающий, без оценивания и медицинских формулировок; дисклеймер
  выводится в карточке рекомендации, настройках и футере.
- Графики нарисованы вручную (SVG) вместо Recharts/Chart.js — минимум
  зависимостей, риск «этапа 6» из раздела 11 ТЗ снят прототипом.
- Удаление записей/задач подтверждается диалогом (`data-confirm`).
