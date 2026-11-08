# Передача проекта «Баланс»

Документ для передачи заказчику: состав файлов, доступы к серверу и инструкция по деплою.

---

## 1. Файлы проекта

**Репозиторий (GitHub):** https://github.com/lazyness680-gif/balans

Состав:

- `app/` — весь код приложения (роутеры, модели, сервисы, шаблоны, статика)
- `tests/` — 43 автотеста (`python -m pytest`)
- `README.md` — описание, запуск, переменные окружения, соответствие ТЗ
- `requirements.txt`, `run.py`, `pytest.ini`, `.gitignore`
- `HANDOVER.md` — этот документ

**Локально у разработчика:** `ТЗ.docx` (техническое задание) — в репозиторий не входит.

**Стек:** Python 3.12 + FastAPI, SQLAlchemy (SQLite, готов к PostgreSQL), Jinja2 + ванильный JS/CSS, графики — собственный SVG, JWT в httpOnly-cookie, bcrypt.

---

## 2. Сервер и доступы

| Параметр | Значение |
|---|---|
| Сервер | VPS, Ubuntu 26.04 |
| IP | `95.163.220.114` |
| Доступ | SSH, пользователь `root`, пароль: `BXvSzkIBaXzUKJxD` |
| Домен | `трекерзерокод2.рф` (+ `www`) |
| HTTPS | ✅ Let's Encrypt, автопродление настроено |
| Каталог приложения | `/opt/balans` |
| База данных | `/opt/balans/data/balans.db` (SQLite) |
| Сервис | `balans.service` (systemd), порт `127.0.0.1:8001`, автозапуск |
| Веб-сервер | nginx (reverse-proxy + статика), конфиг `/etc/nginx/sites-available/balans` |
| Логи | `journalctl -u balans -f` |

**Демо-доступ:** `demo@demo.ru` / `demo1234`

> ⚠️ Пароль SSH и пароль demo-аккаунта — рабочие, их нужно сменить перед передачей клиенту.

---

## 3. Инструкция по деплою

### Первичная установка (на новый сервер)

```bash
# 1. Загрузить код (git clone или архив) в /opt/balans
cd /opt/balans

# 2. Виртуальное окружение и зависимости
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Секреты и база
cat > .env <<'EOF'
BALANS_SECRET_KEY=<сгенерировать>
BALANS_DATABASE_URL=sqlite:////opt/balans/data/balans.db
BALANS_COOKIE_SECURE=1
EOF
mkdir -p data
set -a && . ./.env && set +a

# 4. systemd-сервис (порт 8001)
#    /etc/systemd/system/balans.service → uvicorn app.main:app --port 8001
systemctl daemon-reload
systemctl enable --now balans

# 5. nginx: reverse-proxy на 127.0.0.1:8001, server_name = домен
nginx -t && systemctl reload nginx

# 6. HTTPS
certbot --nginx -d <домен> -d www.<домен> --redirect

# 7. Демо-данные (по желанию)
set -a && . ./.env && set +a && .venv/bin/python -m app.seed
```

### Обновление на работающем сервере

```bash
cd /opt/balans
# получить новый код (git pull или распаковать архив поверх)
.venv/bin/pip install -r requirements.txt   # если изменились зависимости
systemctl restart balans
curl -s http://127.0.0.1:8001/health        # должно быть {"status":"ok"}
```

### Проверка после деплоя

| Проверка | Ожидаемый результат |
|---|---|
| `systemctl is-active balans` | `active` |
| `curl http://127.0.0.1:8001/health` | `{"status":"ok"}` |
| `https://трекерзерокод2.рф/login` | 200, страница входа |
| Вход demo | редирект на `/today` |
| `nginx -t` | `syntax is ok` |

---

## 4. Что не входит в передачу

- Чужой проект на том же сервере (`tracker.service`, домен `трекерзерокод1.рф`) — не относится к «Балансу», не изменять.
- Порт 8000 занят этим проектом — «Баланс» работает на 8001.

---

## 5. Ссылки

- Сайт: https://xn--2-gtbcaaltd9abodcu.xn--p1ai (трекерзерокод2.рф)
- Репозиторий: https://github.com/lazyness680-gif/balans
