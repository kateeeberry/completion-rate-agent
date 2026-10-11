"""Тестова імітація схеми навчальної БД у SQLite (схема `public` підключається через ATTACH).

Це лише тестові дані для перевірки коду. Реальна БД у тестах не використовується.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools  # noqa: E402

COURSES = [
    # course_id, course, level, domain, partner
    ("c1", "Course One", "Beginner", "D1", "P1"),
    ("c2", "Course Two", "Advanced", "D2", "P1"),
    ("c3", "Course Three", "Beginner", "D1", "P2"),
]


def build_enrollments():
    """(enrollment_id, user_id, course_id, funnel_state, completed_at)"""
    rows, n = [], 0

    def add(course, count, certified, extra_completed=0):
        nonlocal n
        states = ["registered", "viewed", "explored"]
        for i in range(count):
            n += 1
            if i < certified:
                state, done = "certified", "2022-05-01"
            elif i < certified + extra_completed:
                state, done = "viewed", "2022-06-01"  # є completed_at, але без сертифіката
            else:
                state, done = states[i % 3], None
            rows.append((f"e{n}", f"u{n % 20}", course, state, done))

    add("c1", 40, certified=10, extra_completed=3)
    add("c2", 35, certified=7)
    add("c3", 5, certified=5)  # нижче порога 30
    return rows


ENROLLMENTS = build_enrollments()


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def attach(dbapi_conn, _):
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS public")

    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE public.dim_course (course_id TEXT, course TEXT, level TEXT, domain TEXT, partner TEXT)"))
        conn.execute(text("CREATE TABLE public.enrollments (enrollment_id TEXT, user_id TEXT, course_id TEXT, funnel_state TEXT, completed_at TEXT)"))
        for c in COURSES:
            conn.execute(text("INSERT INTO public.dim_course VALUES (:a,:b,:c,:d,:e)"), dict(zip("abcde", c)))
        for e in ENROLLMENTS:
            conn.execute(text("INSERT INTO public.enrollments VALUES (:a,:b,:c,:d,:e)"), dict(zip("abcde", e)))
    tools.set_engine(eng)
    yield eng
    tools.set_engine(None)
