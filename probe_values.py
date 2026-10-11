"""DIG, крок 2 (Introspection), частина 2: розподіли ключових полів для визначення метрик.

Тільки агрегати (GROUP BY / COUNT / MIN / MAX), без рядків із даними й без user_id.
Лише SELECT у read-only транзакції. Результат: друк у консоль + values_report.md (у .gitignore).

Запуск:  python probe_values.py
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

QUERIES = [
    (
        "enrollments: funnel_state x completed_at x is_certified",
        """
        SELECT funnel_state,
               COUNT(*) AS n,
               COUNT(completed_at) AS with_completed_at,
               SUM(is_certified) AS certified,
               SUM(CASE WHEN progress_pct = 100 THEN 1 ELSE 0 END) AS progress_100,
               ROUND(MIN(progress_pct), 1) AS min_progress,
               ROUND(MAX(progress_pct), 1) AS max_progress
        FROM public.enrollments
        GROUP BY funnel_state
        ORDER BY n DESC
        """,
    ),
    (
        "enrollments: загальні перевірки",
        """
        SELECT COUNT(*) AS n,
               COUNT(completed_at) AS with_completed_at,
               SUM(CASE WHEN progress_pct = 100 THEN 1 ELSE 0 END) AS progress_100,
               SUM(CASE WHEN completed_at IS NOT NULL AND progress_pct < 100 THEN 1 ELSE 0 END) AS completed_but_lt100,
               SUM(CASE WHEN completed_at IS NULL AND progress_pct = 100 THEN 1 ELSE 0 END) AS p100_without_completed_at,
               SUM(CASE WHEN is_certified = 1 AND completed_at IS NULL THEN 1 ELSE 0 END) AS certified_without_completed_at,
               MIN(enrolled_at) AS min_enrolled_at, MAX(enrolled_at) AS max_enrolled_at,
               MIN(completed_at) AS min_completed_at, MAX(completed_at) AS max_completed_at
        FROM public.enrollments
        """,
    ),
    (
        "payments: plan x is_refunded x amount_usd",
        """
        SELECT plan, is_refunded, amount_usd, COUNT(*) AS n
        FROM public.payments
        GROUP BY plan, is_refunded, amount_usd
        ORDER BY plan, is_refunded, amount_usd
        """,
    ),
    (
        "payments: діапазон дат",
        "SELECT MIN(paid_at) AS min_paid_at, MAX(paid_at) AS max_paid_at FROM public.payments",
    ),
    (
        "users: plan",
        "SELECT plan, COUNT(*) AS n FROM public.users GROUP BY plan ORDER BY n DESC",
    ),
    (
        "dim_course: level",
        "SELECT level, COUNT(*) AS n FROM public.dim_course GROUP BY level ORDER BY n DESC",
    ),
    (
        "зв'язки: enrollments -> users / dim_course (осиротілі ключі)",
        """
        SELECT
          (SELECT COUNT(*) FROM public.enrollments e
             LEFT JOIN public.users u ON u.user_id = e.user_id
             WHERE u.user_id IS NULL) AS enrollments_without_user,
          (SELECT COUNT(*) FROM public.enrollments e
             LEFT JOIN public.dim_course c ON c.course_id = e.course_id
             WHERE c.course_id IS NULL) AS enrollments_without_course,
          (SELECT COUNT(*) FROM public.payments p
             LEFT JOIN public.users u ON u.user_id = p.user_id
             WHERE u.user_id IS NULL) AS payments_without_user
        """,
    ),
]


def main() -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL не знайдено. Заповни .env.")

    engine = create_engine(url)
    out: list[str] = ["# Розподіли ключових полів (лише агрегати)\n"]

    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        for title, sql in QUERIES:
            res = conn.execute(text(sql))
            cols = list(res.keys())
            out.append(f"\n## {title}\n")
            out.append("| " + " | ".join(cols) + " |")
            out.append("|" + "---|" * len(cols))
            for row in res.fetchall():
                out.append("| " + " | ".join(str(v) for v in row) + " |")

    report = "\n".join(out) + "\n"
    print(report)
    with open("values_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Збережено: values_report.md")


if __name__ == "__main__":
    main()
