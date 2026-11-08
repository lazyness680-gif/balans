"""AC-6, AC-7, AC-8: задачи — CRUD, статусы, учёт выполнения по дате планирования (FR-13…FR-19)."""
from __future__ import annotations

from conftest import add_entry, add_entry_raw, add_task_raw, days_ago, moscow_today, register


def test_create_task_with_all_fields_ac6(client):
    register(client)
    response = client.post(
        "/api/tasks",
        json={
            "title": "Отчёт",
            "planned_date": moscow_today().isoformat(),
            "deadline": (moscow_today()).isoformat(),
            "priority": "высокий",
            "category": "работа",
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["title"] == "Отчёт"
    assert task["priority"] == "высокий"
    assert task["category"] == "работа"
    assert task["status"] == "planned"
    assert task["completed_at"] is None

    # страница «Задачи» показывает форму создания со всеми полями (AC-6)
    page = client.get("/tasks").text
    assert 'name="deadline"' in page
    assert 'name="priority"' in page
    assert 'name="category"' in page


def test_task_validation(client):
    register(client)
    assert client.post("/api/tasks", json={"title": "  ", "planned_date": moscow_today().isoformat()}).status_code == 422
    assert client.post(
        "/api/tasks", json={"title": "x", "planned_date": moscow_today().isoformat(), "category": "нет такого"}
    ).status_code == 422
    assert client.post(
        "/api/tasks", json={"title": "x", "planned_date": moscow_today().isoformat(), "priority": "эпично"}
    ).status_code == 422


def test_toggle_done_and_cancel_ac7(client):
    register(client)
    task = client.post(
        "/api/tasks", json={"title": "Спорт", "planned_date": moscow_today().isoformat()}
    ).json()

    # отметить «выполнена»
    response = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["completed_at"] is not None

    # отменить выполнение
    response = client.patch(f"/api/tasks/{task['id']}", json={"status": "planned"})
    assert response.status_code == 200
    assert response.json()["status"] == "planned"
    assert response.json()["completed_at"] is None

    # счётчик выполненных на странице меняется (через форму переключения)
    page = client.post(
        f"/tasks/{task['id']}/toggle", data={"next": "/today"}, follow_redirects=True
    )
    assert page.status_code == 200
    assert 'aria-pressed="true"' in page.text or "1/1" in page.text

    # статус отменена
    response = client.patch(f"/api/tasks/{task['id']}", json={"status": "cancelled"})
    assert response.json()["status"] == "cancelled"
    assert response.json()["completed_at"] is None


def test_completed_counted_by_planned_date_ac8(client, app):
    """«Выполненная за день» = planned_date = день + статус «выполнена» (AC-8)."""
    register(client)
    day = moscow_today()

    # задача на сегодня выполнена
    t1 = client.post("/api/tasks", json={"title": "сегодня", "planned_date": day.isoformat()}).json()
    client.patch(f"/api/tasks/{t1['id']}", json={"status": "done"})

    # задача на завтра выполнена — в сегодняшнюю статистику не идёт
    from datetime import timedelta

    tomorrow = (day + timedelta(days=1)).isoformat()
    t2 = client.post("/api/tasks", json={"title": "завтра", "planned_date": tomorrow}).json()
    client.patch(f"/api/tasks/{t2['id']}", json={"status": "done"})

    # перенос задачи со вчера на сегодня меняет учёт (FR-18: учёт по planned_date)
    t3 = client.post(
        "/api/tasks", json={"title": "переносимая", "planned_date": days_ago(1).isoformat()}
    ).json()
    client.patch(f"/api/tasks/{t3['id']}", json={"status": "done"})
    analytics = client.get("/api/analytics?period=7").json()
    yesterday = [d for d in analytics["days"] if d["date"] == days_ago(1).isoformat()][0]
    assert yesterday["completed"] == 1

    client.patch(f"/api/tasks/{t3['id']}", json={"planned_date": day.isoformat()})
    analytics = client.get("/api/analytics?period=7").json()
    today_row = [d for d in analytics["days"] if d["date"] == day.isoformat()][0]
    yesterday = [d for d in analytics["days"] if d["date"] == days_ago(1).isoformat()][0]
    assert today_row["completed"] == 2
    assert yesterday["completed"] == 0


def test_task_filters(client):
    register(client)
    today = moscow_today().isoformat()
    client.post("/api/tasks", json={"title": "Рабочая", "planned_date": today, "category": "работа"})
    client.post("/api/tasks", json={"title": "Дом", "planned_date": today, "category": "дом"})
    client.post("/api/tasks", json={"title": "Отменённая", "planned_date": today, "status": "cancelled"})

    assert len(client.get("/api/tasks").json()) == 3
    assert len(client.get("/api/tasks?category=дом").json()) == 1
    assert len(client.get(f"/api/tasks?date={today}").json()) == 3
    assert len(client.get("/api/tasks?status=cancelled").json()) == 1
    assert len(client.get("/api/tasks?status=planned&category=работа").json()) == 1

    # фильтры и на странице (FR-17)
    page = client.get("/tasks?status=planned&category=дом").text
    assert "Дом" in page
    assert "Рабочая" not in page


def test_delete_task_ac(client):
    register(client)
    task = client.post(
        "/api/tasks", json={"title": "Удаляемая", "planned_date": moscow_today().isoformat()}
    ).json()

    page = client.get("/tasks").text
    assert "data-confirm" in page  # подтверждение удаления (FR-16)

    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert client.get("/api/tasks").json() == []
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 404


def test_task_edit_via_page(client):
    register(client)
    task = client.post(
        "/api/tasks", json={"title": "Была", "planned_date": moscow_today().isoformat()}
    ).json()

    response = client.post(
        "/tasks/task",
        data={
            "action": "edit",
            "id": str(task["id"]),
            "title": "Стала",
            "planned_date": moscow_today().isoformat(),
            "priority": "высокий",
            "category": "дом",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    updated = client.get("/api/tasks").json()[0]
    assert updated["title"] == "Стала"
    assert updated["priority"] == "высокий"
