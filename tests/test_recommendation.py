"""AC-9…AC-15: рекомендация по нагрузке — все ветки алгоритма (раздел 6 ТЗ)."""
from __future__ import annotations

from conftest import add_entry, add_task_raw, days_ago, moscow_today, register

from app.services.recommendation import (
    apply_completion,
    base_limit,
    compute_max_tasks,
    plural_tasks,
)


# ---------- Чистая логика (п.6.1 ТЗ) ----------

def test_base_limit_branches():
    assert base_limit(mood_today=1, stress_today=3) == 3   # низкое настроение
    assert base_limit(mood_today=4, stress_today=9) == 3   # высокий стресс
    assert base_limit(mood_today=3, stress_today=2) == 5   # среднее настроение
    assert base_limit(mood_today=4, stress_today=5) == 5   # умеренный стресс
    assert base_limit(mood_today=5, stress_today=2) == 7   # всё хорошо
    assert base_limit(mood_today=4, stress_today=6) == 5


def test_completion_penalty_ac11():
    assert apply_completion(7, 0.4) == 5   # −2
    assert apply_completion(3, 0.1) == 1   # не ниже 1
    assert apply_completion(3, 0.5) == 3   # ровно 50% — без штрафа
    assert apply_completion(7, None) == 7  # данных нет — без штрафа


def test_comfort_limit_ac12():
    assert compute_max_tasks(5, 2, 1.0, comfort_limit=4) == 4
    assert compute_max_tasks(5, 2, 1.0, comfort_limit=10) == 7  # лимит не мешает


def test_plural_tasks():
    assert plural_tasks(1) == "задачи"
    assert plural_tasks(2) == "задачи"
    assert plural_tasks(5) == "задач"
    assert plural_tasks(11) == "задач"


# ---------- API рекомендации ----------

def test_recommendation_after_saving_ac9(client):
    register(client)
    add_entry(client, moscow_today(), mood=4, stress=3)

    response = client.get("/api/recommendations/today")
    assert response.status_code == 200
    body = response.json()
    assert body["state_missing"] is False
    assert isinstance(body["max_tasks"], int)
    assert "не больше" in body["text"]
    assert body["explanation"]                      # объяснение «почему столько»
    assert body["basis"]["mood_today"] == 4
    assert body["basis"]["stress_today"] == 3
    assert "медицинская" in body["disclaimer"]      # дисклеймер (FR-25)

    # карточка на странице «Сегодня» показывает число задач и объяснение
    page = client.get("/today").text
    assert "Рекомендация на сегодня" in page
    assert "Почему столько" in page


def test_high_stress_caps_at_three_ac10(client):
    register(client)
    add_entry(client, moscow_today(), mood=4, stress=8)
    body = client.get("/api/recommendations/today").json()
    assert body["max_tasks"] <= 3
    assert any("высокий стресс" in f for f in body["basis"]["factors"])

    # настроение ≤ 2 тоже даёт ≤ 3
    add_entry(client, moscow_today(), mood=1, stress=3)
    body = client.get("/api/recommendations/today").json()
    assert body["max_tasks"] <= 3
    assert any("низкое настроение" in f for f in body["basis"]["factors"])


def test_low_completion_lowers_recommendation_ac11(client, app):
    register(client)
    add_entry(client, moscow_today(), mood=5, stress=2)

    # база при хорошем состоянии = 7, штрафа ещё нет
    assert client.get("/api/recommendations/today").json()["max_tasks"] == 7

    # 1 задача выполнена из 4 запланированных = 25% < 50% → 7 − 2 = 5
    for offset in (1, 2, 3, 4):
        add_task_raw(app, 1, f"задача {offset}", days_ago(offset))
    done = app.state.db.session()
    from app.models import Task

    tasks = done.query(Task).filter(Task.title == "задача 1").all()
    for task in tasks:
        task.status = "done"
    done.commit()
    done.close()

    body = client.get("/api/recommendations/today").json()
    assert body["basis"]["completion_rate_7"] == 0.25
    assert body["max_tasks"] == 5
    assert any("процент выполнения" in f for f in body["basis"]["factors"])

    # не может упасть ниже 1
    assert compute_max_tasks(1, 9, 0.0, None) == 1


def test_comfort_limit_caps_recommendation_ac12(client):
    register(client)
    assert client.patch("/api/me", json={"comfort_limit": 2}).status_code == 200
    add_entry(client, moscow_today(), mood=5, stress=2)

    body = client.get("/api/recommendations/today").json()
    assert body["max_tasks"] == 2
    assert body["basis"]["comfort_limit"] == 2
    assert any("личный лимит" in f for f in body["basis"]["factors"])

    # и настройка работает через страницу настроек (FR-38)
    response = client.post(
        "/settings",
        data={"comfort_limit": "4", "theme": "light", "timezone": "Europe/Moscow"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert client.get("/api/me").json()["comfort_limit"] == 4


def test_soft_hint_when_planned_exceeds_ac13(client):
    register(client)
    add_entry(client, moscow_today(), mood=1, stress=9)   # ориентир ≤ 3

    for i in range(5):
        client.post(
            "/api/tasks",
            json={"title": f"нагрузка {i}", "planned_date": moscow_today().isoformat()},
        )

    body = client.get("/api/recommendations/today").json()
    assert body["max_tasks"] <= 3
    assert body["planned_today"] == 5
    assert "больше ориентира" in body["explanation"]

    # блокировки нет: задачу можно добавить и дальше (FR-24)
    response = client.post(
        "/api/tasks",
        json={"title": "ещё одна", "planned_date": moscow_today().isoformat()},
    )
    assert response.status_code == 201

    page = client.get("/today").text
    assert "ничего менять не нужно" in page


def test_state_missing_card_ac14(client):
    """Отметки нет, но задачи есть → карточка без числа задач в рекомендации."""
    register(client)
    for i in range(3):
        client.post(
            "/api/tasks",
            json={"title": f"план {i}", "planned_date": moscow_today().isoformat()},
        )

    body = client.get("/api/recommendations/today").json()
    assert body["state_missing"] is True
    assert body["max_tasks"] is None          # рекомендации по числу задач нет
    assert body["planned_today"] == 3         # показывается только факт планов
    assert "не больше" not in body["text"]

    page = client.get("/today").text
    assert "Состояние не отмечено" in page
    assert "Отметить состояние" in page


def test_state_missing_hint_about_average(client, app):
    """Если план выше обычного — подсказка «обычно вы планируете ~K задач» (п.6.2)."""
    register(client)
    for offset in (1, 2, 3, 4, 5, 6):
        add_task_raw(app, 1, "обычная", days_ago(offset))   # обычно ~1 в день
    for i in range(4):
        client.post(
            "/api/tasks",
            json={"title": f"сегодня {i}", "planned_date": moscow_today().isoformat()},
        )

    body = client.get("/api/recommendations/today").json()
    assert body["state_missing"] is True
    assert body["hint"] is not None
    assert "Обычно вы планируете" in body["hint"]

    # после сохранения отметки карточка становится обычной рекомендацией (п.6.2)
    add_entry(client, moscow_today(), mood=5, stress=2)
    body = client.get("/api/recommendations/today").json()
    assert body["state_missing"] is False
    assert body["max_tasks"] is not None


def test_banner_on_login_and_hidden_after_entry_ac15(client):
    register(client)

    # при входе без отметки — in-app баннер (FR-27)
    page = client.get("/today").text
    assert 'class="banner"' in page
    assert "Отметьте состояние" in page

    # сохраняем отметку — баннер скрывается (FR-29)
    response = client.post(
        "/today/entry",
        data={"mood": "4", "stress": "4"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert 'class="banner"' not in response.text
    assert "Рекомендация на сегодня" in response.text

    # рекомендация пересчиталась после сохранения (FR-20)
    body = client.get("/api/recommendations/today").json()
    assert body["state_missing"] is False
    assert body["basis"]["mood_today"] == 4


def test_recommendation_recalculates_after_task_change_ac20(client):
    register(client)
    add_entry(client, moscow_today(), mood=5, stress=2)
    assert client.get("/api/recommendations/today").json()["planned_today"] == 0

    client.post("/api/tasks", json={"title": "а", "planned_date": moscow_today().isoformat()})
    body = client.get("/api/recommendations/today").json()
    assert body["planned_today"] == 1          # учтены запланированные (FR-22)

    task_id = client.get("/api/tasks").json()[0]["id"]
    client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
    assert client.get("/api/recommendations/today").json()["planned_today"] == 0
