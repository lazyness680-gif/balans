"""AC-1, AC-2: аккаунт, вход/выход, изоляция данных, rate limiting (FR-1…FR-4)."""
from __future__ import annotations

from conftest import add_entry, moscow_today, register


def test_register_and_login_ac1(client):
    # регистрация по email + пароль, без подтверждения email (FR-1)
    profile = register(client, "alice@example.com")
    assert profile["email"] == "alice@example.com"
    assert "password" not in profile

    # сразу виден профиль — вход выполнен (cookie выдана)
    me = client.get("/api/me")
    assert me.status_code == 200

    # выход
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401

    # повторный вход (FR-2)
    login = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "secret12"}
    )
    assert login.status_code == 200
    assert client.get("/api/me").status_code == 200


def test_wrong_password(client):
    register(client, "bob@example.com")
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login", json={"email": "bob@example.com", "password": "wrong-pass"}
    )
    assert response.status_code == 401


def test_duplicate_email(client):
    register(client, "dup@example.com")
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register", json={"email": "dup@example.com", "password": "another1"}
    )
    assert response.status_code == 409


def test_invalid_email_and_short_password(client):
    response = client.post(
        "/api/auth/register", json={"email": "не-почта", "password": "secret12"}
    )
    assert response.status_code == 422
    response = client.post(
        "/api/auth/register", json={"email": "ok@example.com", "password": "123"}
    )
    assert response.status_code == 422


def test_guest_sees_only_login(make_client):
    """Гость (не авторизован) видит экран входа, данных нет (раздел 4 ТЗ)."""
    guest = make_client()
    assert guest.get("/today", follow_redirects=False).status_code == 303
    assert guest.get("/api/me").status_code == 401
    assert guest.get("/api/tasks").status_code == 401
    login_page = guest.get("/login", follow_redirects=True)
    assert login_page.status_code == 200
    assert "Вход" in login_page.text


def test_data_isolation_ac2(make_client):
    """Пользователь видит только свои записи и задачи (AC-2, FR-3)."""
    alice = make_client()
    bob = make_client()
    alice_profile = register(alice, "alice2@example.com")
    register(bob, "bob2@example.com")

    entry = add_entry(alice, moscow_today(), mood=2, stress=9, note="только моё")
    task = alice.post(
        "/api/tasks", json={"title": "моя задача", "planned_date": moscow_today().isoformat()}
    ).json()

    # у Боба пусто
    assert bob.get("/api/mood-entries").json() == []
    assert bob.get("/api/tasks").json() == []

    # чужие ID недоступны (404, не 403 — не раскрываем существование)
    assert bob.get(f"/api/mood-entries/{entry['id']}").status_code in (404, 405)
    assert bob.patch(
        f"/api/mood-entries/{entry['id']}", json={"mood": 5}
    ).status_code == 404
    assert bob.patch(
        f"/api/tasks/{task['id']}", json={"status": "done"}
    ).status_code == 404
    assert bob.delete(f"/api/tasks/{task['id']}").status_code == 404

    # страницы тоже не показывают чужое
    history = bob.get("/history").text
    assert "только моё" not in history
    assert "alice2@example.com" not in bob.get("/settings").text

    # а у Алисы — своё
    assert any(
        item["id"] == task["id"] for item in alice.get("/api/tasks").json()
    )
    assert alice_profile["email"] == "alice2@example.com"


def test_auth_rate_limit(client):
    """Rate limiting на вход (раздел 11 ТЗ: митигация спам-регистраций)."""
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "nope123"})
    response = client.post(
        "/api/auth/login", json={"email": "x@example.com", "password": "nope123"}
    )
    assert response.status_code == 429


def test_page_form_errors_redirect_with_message(client):
    """HTML-формы не получают «сырой» JSON: 303 + параметр error (UI на русском)."""
    # нет поля email — как в скриншоте (422 раньше отдавался JSON)
    response = client.post("/register", data={"password": "secret12"}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/register?error=")
    assert "email" in location  # «Укажите email» (URL-encoded)

    # невалидный email и короткий пароль — одно сообщение с обоими полями
    response = client.post(
        "/register", data={"email": "bad", "password": "1"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]

    # редирект ведёт на страницу с русским сообщением, а не на JSON
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "alert-error" in page.text

    # API по-прежнему отдаёт JSON 422 (контракт п.3.3 ТЗ)
    api = client.post("/api/auth/register", data={"password": "secret12"})
    assert api.status_code == 422
    assert api.headers["content-type"].startswith("application/json")


def test_page_rate_limit_redirects(client):
    """429 на страницах входа/регистрации — редирект с сообщением, не JSON."""
    for _ in range(11):
        client.post("/login", data={"email": "x@example.com", "password": "nope123"},
                    follow_redirects=False)
    response = client.post(
        "/login", data={"email": "x@example.com", "password": "nope123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?error=")
