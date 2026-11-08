"""AC-16…AC-22: аналитика, дайджест, темы, настройки (раздел 5.6–5.7)."""
from __future__ import annotations

from conftest import add_entry, add_entry_raw, add_task_raw, days_ago, moscow_today, register


def _seed_week(app, user_id: int = 1) -> None:
    """7 дней отметок + немного задач — для графиков и дайджеста."""
    moods = [5, 4, 4, 3, 4, 5, 4]
    stresses = [3, 4, 4, 6, 5, 3, 3]
    for offset in range(7):
        day = days_ago(offset)
        add_entry_raw(app, user_id, day, mood=moods[offset], stress=stresses[offset],
                      tags=["работа"] if offset % 2 == 0 else ["сон"])
        add_task_raw(app, user_id, f"задача-{offset}", day)
        if offset % 2 == 0:
            add_task_raw(app, user_id, f"выполнено-{offset}", day, status="done")


def test_analytics_shape_ac16_ac18(client, app):
    register(client)
    _seed_week(app)

    data = client.get("/api/analytics?period=7").json()
    assert data["period"] == 7
    assert len(data["days"]) == 7
    assert data["empty"] is False

    day = [d for d in data["days"] if d["date"] == days_ago(0).isoformat()][0]
    # tooltip (AC-18) собирается из этих полей: дата, настроение, стресс, выполненные
    assert day["mood"] == 5
    assert day["stress"] == 3
    assert isinstance(day["completed"], int)

    # график 2 — отдельные данные стресса (AC-17): шкала не смешивается
    assert all(d["stress"] is None or 1 <= d["stress"] <= 10 for d in data["days"])
    assert all(d["mood"] is None or 1 <= d["mood"] <= 5 for d in data["days"])

    # страница содержит оба графика
    page = client.get("/analytics").text
    assert 'id="chart-mood"' in page
    assert 'id="chart-stress"' in page
    assert "настроение (1–5)" in page
    assert "стресс (1–10)" in page


def test_analytics_periods_ac32(client, app):
    register(client)
    _seed_week(app)
    add_entry_raw(app, 1, days_ago(20), mood=3, stress=7)

    assert len(client.get("/api/analytics?period=7").json()["days"]) == 7
    assert len(client.get("/api/analytics?period=30").json()["days"]) == 30
    assert len(client.get("/api/analytics?period=90").json()["days"]) == 90
    # некорректный период → по умолчанию 7
    assert client.get("/api/analytics?period=13").json()["period"] == 7

    # переключатели периода есть на странице
    page = client.get("/analytics").text
    for value in ("7", "30", "90"):
        assert f'data-period="{value}"' in page


def test_tag_filter_ac19(client, app):
    register(client)
    _seed_week(app)
    # вне фильтра — запись с другим тегом
    add_entry_raw(app, 1, days_ago(10), mood=1, stress=10, tags=["спорт"])

    all_data = client.get("/api/analytics?period=30").json()
    assert all_data["days_with_data"] == 8

    filtered = client.get("/api/analytics?period=30&tags=работа").json()
    assert filtered["days_with_data"] == 4
    assert all(d["mood"] is None for d in filtered["days"] if d["date"] == days_ago(10).isoformat())

    # чекбоксы тегов на странице
    page = client.get("/analytics").text
    for tag in ("сон", "работа", "здоровье", "спорт"):
        assert f'value="{tag}"' in page


def test_empty_state_less_than_3_days_ac20(client):
    register(client)
    add_entry(client, moscow_today())

    data = client.get("/api/analytics?period=7").json()
    assert data["days_with_data"] == 1
    assert data["empty"] is True

    add_entry(client, days_ago(2))
    data = client.get("/api/analytics?period=7").json()
    assert data["days_with_data"] == 2
    assert data["empty"] is True    # всё ещё < 3 дней

    add_entry(client, days_ago(3))
    data = client.get("/api/analytics?period=7").json()
    assert data["days_with_data"] == 3
    assert data["empty"] is False


def test_digest_week_and_month_ac21(client, app):
    register(client)
    _seed_week(app)

    week = client.get("/api/digest?period=week").json()
    assert week["current"]["avg_mood"] is not None
    assert week["current"]["avg_stress"] is not None
    assert week["current"]["completion_rate_text"].endswith("%")
    assert week["current"]["days_with_entries"] == 7
    assert week["length_days"] == 7

    month = client.get("/api/digest?period=month").json()
    assert month["length_days"] == 30

    # период без предыдущих данных — честное «мало данных» (п.6.3)
    assert "мало данных" in week["trend"]["text"]

    # есть сравнение с прошлым периодом — тренд по существу
    for offset in range(8, 15):
        add_entry_raw(app, 1, days_ago(offset), mood=5, stress=8)   # было: стресс выше
    week = client.get("/api/digest?period=week").json()
    assert "стресс" in week["trend"]["text"]
    assert week["trend"]["direction"] in ("worse", "better", "flat")

    # дайджест на странице
    page = client.get("/analytics").text
    assert "Дайджест" in page
    assert 'id="digest-week"' in page


def test_theme_toggle_and_persistence_ac22(client):
    register(client)
    assert client.get("/api/me").json()["theme"] == "light"

    response = client.patch("/api/me", json={"theme": "dark"})
    assert response.status_code == 200
    assert response.json()["theme"] == "dark"

    # тема применяется к разметке и сохраняется (AC-22)
    page = client.get("/today").text
    assert 'data-theme="dark"' in page

    response = client.patch("/api/me", json={"theme": "neon"})
    assert response.status_code == 422


def test_settings_timezone_and_comfort_limit(client):
    register(client)
    response = client.post(
        "/settings",
        data={"comfort_limit": "6", "theme": "dark", "timezone": "Asia/Yakutsk"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    profile = client.get("/api/me").json()
    assert profile["comfort_limit"] == 6
    assert profile["timezone"] == "Asia/Yakutsk"
    assert profile["theme"] == "dark"

    # некорректный пояс и лимит не проходят
    response = client.post(
        "/settings",
        data={"comfort_limit": "50", "timezone": "Mars/Olympus"},
        follow_redirects=True,
    )
    page = response.text
    assert "от 1 до 30" in page or "Неизвестный часовой пояс" in page

    # «сегодня» считается по часовому поясу пользователя (FR-4)
    from app.dates import today_in

    assert today_in("Asia/Yakutsk") is not None

    # API тоже валидирует пояс
    assert client.patch("/api/me", json={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.patch("/api/me", json={"timezone": "UTC"}).status_code == 200


def test_recommended_endpoints_exist():
    """Контракт API из п.3.3 ТЗ — все эндпоинты на месте."""
    from app.config import Config
    from app.main import create_app

    app = create_app(Config(database_url="sqlite:///:memory:"))
    paths = set(app.openapi().get("paths", {}))
    expected = {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/me",
        "/api/mood-entries",
        "/api/mood-entries/{entry_id}",
        "/api/tasks",
        "/api/tasks/{task_id}",
        "/api/recommendations/today",
        "/api/analytics",
        "/api/digest",
    }
    missing = expected - paths
    assert not missing, f"Отсутствуют эндпоинты: {missing}"
