"""DIG, крок 1-2 (Describe -> Introspection): розвідка схеми БД перед написанням агента.

Що робить:
  - підключається до БД за DATABASE_URL з .env (рядок підключення в код не пишемо);
  - відкриває кожну транзакцію як READ ONLY, виконує лише SELECT;
  - для кожної таблиці виводить колонки, типи, кількість рядків, частку NULL, кількість унікальних значень;
  - НЕ виводить значень з рядків, лише агрегати (щоб у звіт не потрапили PII).

Запуск:  python probe_schema.py
Результат: друк у консоль + файл schema_report.md (він у .gitignore).
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

SKIP_SCHEMAS = ("pg_catalog", "information_schema")


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL не знайдено. Скопіюй .env.example у .env і заповни його.")

    engine = create_engine(url)
    lines: list[str] = ["# Звіт про схему БД (лише агрегати, без значень рядків)\n"]

    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))

        db_name = conn.execute(text("SELECT current_database()")).scalar()
        lines.append(f"База: `{db_name}`\n")

        tables = conn.execute(
            text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )
        ).fetchall()

        for schema, table in tables:
            full = f"{quote(schema)}.{quote(table)}"
            n_rows = conn.execute(text(f"SELECT COUNT(*) FROM {full}")).scalar()
            lines.append(f"\n## {schema}.{table}: {n_rows} рядків\n")
            lines.append("| колонка | тип | % NULL | унікальних |")
            lines.append("|---|---|---|---|")

            cols = conn.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = :s AND table_name = :t
                    ORDER BY ordinal_position
                    """
                ),
                {"s": schema, "t": table},
            ).fetchall()

            for col, dtype in cols:
                c = quote(col)
                stats = conn.execute(
                    text(f"SELECT COUNT(*) - COUNT({c}), COUNT(DISTINCT {c}) FROM {full}")
                ).one()
                nulls, distinct = stats
                pct = round(100 * nulls / n_rows, 1) if n_rows else 0
                lines.append(f"| {col} | {dtype} | {pct} | {distinct} |")

    report = "\n".join(lines) + "\n"
    print(report)
    with open("schema_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Збережено: schema_report.md")


if __name__ == "__main__":
    main()
