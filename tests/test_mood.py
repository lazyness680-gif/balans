"""AC-3, AC-4, AC-5: записи настроения/стресса, шкалы, теги, границы дат (FR-5…FR-12)."""
from __future__ import annotations

from conftest import add_entry, days_ago, moscow_today, register


def test_create_entry_and_see_in_history_ac3(client):
    register(client)
    today = moscow_today()

    response = client.post(
        "/api/mood-entries",
        json={
            "date": today.isoformat(),
            "mood": 4,
            "stress": 6,
            "note": "нормальный день",
            "tags": ["работа", "сон"],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mood"] == 4
    assert body["stress"] == 6
    assert body["tags"] == ["сон", "работа"]  # порядок фиксированного набора

    # запись видна в истории (FR-10)
    history = client.get("/history").text
    assert "нормальный день" in history
    assert "работа" in history

    # и в списке API
    entries = client.get("/api/mood-entries").json()
    assert len(entries) == 1


def test_scales_and_note_limits(client):
    register(client)
    today = moscow_today().isoformat()

    assert client.post(
        "/api/mood-entries", json={"date": today, "mood": 6, "stress": 5}
    ).status_code == 422
    assert client.post(
        "/api/mood-entries", json={"date": today, "mood": 0, "stress": 5}
    ).status_code == 422
    assert client.post(
        "/api/mood-entries", json={"date": today, "mood": 3, "stress": 11}
    ).status_code == 422
    assert client.post(
        "/api/mood-entries", json={"date": today, "mood": 3, "stress": 0}
    ).status_code == 422
    assert client.post(
        "/api/mood-entries", json={"date": today, "mood": 3, "stress": 5, "note": "я" * 501}
    ).status_code == 422
    assert client.post(
        "/api/mood-entries",
        json={"date": today, "mood": 3, "stress": 5, "tags": ["космос"]},
    ).status_code == 422
    # валидные пограничные значения проходят
    assert client.post(
        "/api/mood-entries",
        json={"date": today, "mood": 5, "stress": 10, "note": "я" * 500},
    ).status_code == 201


def test_one_entry_per_date_upsert_ac4(client):
    register(client)
    today = moscow_today()

    first = add_entry(client, today, mood=2, stress=8, note="первая версия")
    second = add_entry(client, today, mood=4, stress=3, note="вторая версия")

    assert first["id"] == second["id"]  # дубль не создаётся
    entries = client.get("/api/mood-entries").json()
    assert len(entries) == 1
    assert entries[0]["mood"] == 4
    assert entries[0]["note"] == "вторая версия"

    # уникальный индекс (user_id, date) закреплён в модели
    from app.models import MoodEntry

    assert any(
        getattr(c, "name", None) == "uq_mood_entries_user_date"
        for c in MoodEntry.__table__.constraints
    )


def test_date_boundaries_ac5(client):
    register(client)

    # создать задним числом можно до 7 дней (FR-7)
    assert client.post(
        "/api/mood-entries",
        json={"date": days_ago(7).isoformat(), "mood": 3, "stress": 3},
    ).status_code == 201
    # восьмой день назад — нельзя
    assert client.post(
        "/api/mood-entries",
        json={"date": days_ago(8).isoformat(), "mood": 3, "stress": 3},
    ).status_code == 422
    # на будущую дату — нельзя (FR-9)
    from datetime import timedelta

    future = (moscow_today() + timedelta(days=1)).isoformat()
    assert client.post(
        "/api/mood-entries", json={"date": future, "mood": 3, "stress": 3}
    ).status_code == 422

    # редактирование: запись старше 3 дней закрыто (FR-8)
    old_entry = add_entry(client, days_ago(4), mood=3, stress=3)
    response = client.patch(f"/api/mood-entries/{old_entry['id']}", json={"mood": 5})
    assert response.status_code == 422

    # запись в пределах 3 дней — редактируется
    fresh_entry = add_entry(client, days_ago(2), mood=3, stress=3)
    response = client.patch(
        f"/api/mood-entries/{fresh_entry['id']}", json={"mood": 5, "stress": 1}
    )
    assert response.status_code == 200
    assert response.json()["mood"] == 5

    # перенос на ещё более старую дату — нельзя
    response = client.patch(
        f"/api/mood-entries/{fresh_entry['id']}", json={"date": days_ago(6).isoformat()}
    )
    assert response.status_code == 422


def test_delete_entry_with_confirmation_flow(client):
    """Удаление из истории с подтверждением (FR-12, Should)."""
    register(client)
    entry = add_entry(client, moscow_today())

    # страница содержит форму удаления с data-confirm (подтверждение в UI)
    page = client.get("/history").text
    assert "data-confirm" in page

    # API-удаление
    assert client.delete(f"/api/mood-entries/{entry['id']}").status_code == 204
    assert client.get("/api/mood-entries").json() == []
    assert client.delete(f"/api/mood-entries/{entry['id']}").status_code == 404


def test_history_filters_by_period(client, app):
    register(client)
    add_entry(client, moscow_today())
    add_entry(client, days_ago(3))

    from conftest import add_entry_raw

    add_entry_raw(app, 1, days_ago(10), mood=5, stress=1)

    week = client.get("/api/mood-entries?from=%s&to=%s" % (
        days_ago(6).isoformat(), moscow_today().isoformat())).json()
    assert len(week) == 2

    page_7 = client.get("/history?period=7").text
    page_30 = client.get("/history?period=30").text
    assert page_7.count("entry-card") == 2
    assert page_30.count("entry-card") == 3
