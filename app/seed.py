"""Наполнение демо-данными (для просмотра графиков и дайджеста).

Запуск:  python -m app.seed
Доступ:  demo@demo.ru / demo1234
"""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from .config import load_config
from .database import configure
from .dates import today_in
from .models import MoodEntry, Task, User
from .security import hash_password

DEMO_EMAIL = "demo@demo.ru"
DEMO_PASSWORD = "demo1234"


def seed(days: int = 45, seed_value: int = 42) -> None:
    rng = random.Random(seed_value)
    db = configure(load_config().database_url)
    db.create_all()

    with db.session() as session:
        user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                timezone="Europe/Moscow",
                comfort_limit=None,
                theme="light",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            print(f"Создан демо-пользователь {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"Демо-пользователь уже есть: {DEMO_EMAIL} / {DEMO_PASSWORD}")

        existing = session.scalar(
            select(MoodEntry.id).where(MoodEntry.user_id == user.id).limit(1)
        )
        if existing is not None:
            print("Данные уже заполнены — пропускаем.")
            return

        today = today_in(user.timezone)
        tags_pool = [["сон"], ["работа"], ["здоровье"], ["спорт"], ["работа", "сон"], []]
        categories = ["работа", "учёба", "дом", "здоровье", "другое"]

        for offset in range(days - 1, 0, -1):
            day = today - timedelta(days=offset)
            mood = max(1, min(5, int(rng.gauss(4, 1))))
            stress = max(1, min(10, int(rng.gauss(5, 2))))
            session.add(
                MoodEntry(
                    user_id=user.id,
                    date=day,
                    mood=mood,
                    stress=stress,
                    note="демо-запись" if offset % 9 == 0 else None,
                    tags=rng.choice(tags_pool),
                )
            )

            for i in range(rng.randint(1, 5)):
                status = rng.choices(
                    ["planned", "done", "cancelled"], weights=[2, 6, 1]
                )[0]
                session.add(
                    Task(
                        user_id=user.id,
                        title=f"Демо-задача {i + 1} ({day.isoformat()})",
                        planned_date=day,
                        priority=rng.choice(["низкий", "средний", "высокий"]),
                        category=rng.choice(categories),
                        status=status,
                    )
                )

        # сегодняшняя задача, чтобы карточка рекомендации была наглядна
        session.add(
            Task(
                user_id=user.id,
                title="Посмотреть демонстрацию трекера",
                planned_date=today,
                priority="средний",
                category="другое",
            )
        )
        session.commit()
        print(f"Заполнено: {days - 1} дней записей и задач.")


if __name__ == "__main__":
    seed()
