"""Детерміновані інструменти аналітики: SQL лише тут, LLM SQL не пише.

Кожна функція:
  - виконує фіксований SELECT у read-only з'єднанні (дані в базі не змінюються);
  - бере визначення метрик із semantic_layer.yaml;
  - повертає словник {title, columns, rows, note, definition} або {title, error}.
Ці ж функції використовує і дашборд (app.py), і агент (agent.py), тому цифри збігаються.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

ROOT = Path(__file__).resolve().parent


def load_semantic_layer(path: Path | None = None) -> dict:
    with open(path or ROOT / "semantic_layer.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


SEM = load_semantic_layer()
COMPLETED = SEM["metrics"]["completed_enrollment"]["sql_condition"]
DEFINITION_TEXT = (
    "Completed = funnel_state = 'certified' (є сертифікат). "
    "Completion rate = завершені записи / усі записи * 100; рахуємо записи на курс, не студентів."
)
DIMENSIONS: dict[str, str] = SEM["dimensions"]
FUNNEL_ORDER: list[str] = SEM["funnel"]["order"]
DEFAULT_TOP_N: int = SEM["defaults"]["top_n"]
DEFAULT_MIN_N: int = SEM["defaults"]["min_enrollments_for_ranking"]

for _name, _col in DIMENSIONS.items():  # захист від випадкової помилки в yaml
    if not re.fullmatch(r"c\.[a-z_]+", _col):
        raise ValueError(f"Некоректний стовпець виміру {_name}: {_col}")

# ---------- підключення -------------------------------------------------------

_engine_override = None


def set_engine(engine) -> None:
    """Для тестів: підставити інший engine."""
    global _engine_override
    _engine_override = engine


@lru_cache(maxsize=1)
def _default_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL не задано. Заповни .env (див. .env.example).")
    return create_engine(url, pool_pre_ping=True)


def get_engine():
    return _engine_override if _engine_override is not None else _default_engine()


_SELECT_ONLY = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy)\b", re.IGNORECASE
)


def run_select(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Виконує лише SELECT/WITH; у PostgreSQL транзакція READ ONLY."""
    if not _SELECT_ONLY.match(sql) or _FORBIDDEN.search(sql):
        raise ValueError("Дозволені лише SELECT-запити.")
    engine = get_engine()
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        return pd.read_sql(text(sql), conn, params=params or {})


# ---------- допоміжне ---------------------------------------------------------


def _rate(completed: int, total: int) -> float | None:
    return round(100.0 * completed / total, 2) if total else None


def _add_rate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("enrollments", "completed"):
        df[col] = df[col].astype(int)
    df["completion_rate_pct"] = [_rate(c, n) for c, n in zip(df["completed"], df["enrollments"])]
    return df


def _pack(title: str, df: pd.DataFrame, note: str = "") -> dict:
    return {
        "title": title,
        "columns": list(df.columns),
        "rows": df.to_dict("records"),
        "note": note,
        "definition": DEFINITION_TEXT,
    }


def _error(title: str, message: str) -> dict:
    return {"title": title, "error": message, "definition": DEFINITION_TEXT}


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


# ---------- інструменти -------------------------------------------------------


def get_overview() -> dict:
    """Загальні показники: кількість записів на курси, завершені записи, completion rate,
    кількість унікальних студентів і контрольна цифра якості даних. Без параметрів."""
    title = "Загальні показники"
    try:
        df = run_select(
            f"""
            SELECT COUNT(*) AS enrollments,
                   SUM(CASE WHEN {COMPLETED} THEN 1 ELSE 0 END) AS completed,
                   COUNT(DISTINCT e.user_id) AS learners,
                   SUM(CASE WHEN e.completed_at IS NOT NULL AND NOT ({COMPLETED})
                            THEN 1 ELSE 0 END) AS completed_at_without_certificate
            FROM public.enrollments e
            """
        )
        out = _add_rate(df.assign(completed=df["completed"].fillna(0)))
        for col in ("learners", "completed_at_without_certificate"):
            out[col] = out[col].astype(int)
        return _pack(title, out, "Рахуємо записи на курс (enrollment).")
    except Exception as exc:  # noqa: BLE001
        return _error(title, f"Не вдалося виконати запит: {type(exc).__name__}")


def get_funnel() -> dict:
    """Воронка: кількість записів на кожному етапі (registered, viewed, explored, certified)
    і частка від усіх записів. Без параметрів."""
    title = "Воронка за funnel_state"
    try:
        df = run_select(
            "SELECT e.funnel_state AS funnel_state, COUNT(*) AS enrollments "
            "FROM public.enrollments e GROUP BY e.funnel_state"
        )
        total = int(df["enrollments"].sum())
        rank = {name: i for i, name in enumerate(FUNNEL_ORDER)}
        df["_o"] = df["funnel_state"].map(lambda s: rank.get(s, len(rank)))
        df = df.sort_values(["_o", "funnel_state"]).drop(columns="_o").reset_index(drop=True)
        df["enrollments"] = df["enrollments"].astype(int)
        df["share_pct"] = [_rate(n, total) for n in df["enrollments"]]
        return _pack(
            title, df, "Порядок етапів — припущення за мінімальним progress_pct (див. semantic_layer.yaml)."
        )
    except Exception as exc:  # noqa: BLE001
        return _error(title, f"Не вдалося виконати запит: {type(exc).__name__}")


def get_completion_by_course(top_n: int = 10, min_enrollments: int = 30, order: str = "best") -> dict:
    """Рейтинг курсів за completion rate.
    top_n: скільки курсів показати (1-50, типово 10).
    min_enrollments: мінімум записів на курс, щоб він потрапив у рейтинг (типово 30).
    order: 'best' (найвищий completion rate) або 'worst' (найнижчий)."""
    title = "Completion rate по курсах"
    if order not in ("best", "worst"):
        return _error(title, "order має бути 'best' або 'worst'.")
    top_n = _clamp(top_n, 1, 50, DEFAULT_TOP_N)
    min_enrollments = _clamp(min_enrollments, 1, 100000, DEFAULT_MIN_N)
    try:
        df = run_select(
            f"""
            SELECT c.course_id AS course_id, c.course AS course, c.level AS level,
                   COUNT(*) AS enrollments,
                   SUM(CASE WHEN {COMPLETED} THEN 1 ELSE 0 END) AS completed
            FROM public.enrollments e
            JOIN public.dim_course c ON c.course_id = e.course_id
            GROUP BY c.course_id, c.course, c.level
            HAVING COUNT(*) >= :min_n
            """,
            {"min_n": min_enrollments},
        )
        if df.empty:
            return _error(title, f"Немає курсів із кількістю записів >= {min_enrollments}.")
        df = _add_rate(df)
        asc = order == "worst"
        df = (
            df.sort_values(
                ["completion_rate_pct", "enrollments", "course_id"], ascending=[asc, False, True]
            )
            .head(top_n)
            .reset_index(drop=True)
        )
        return _pack(title, df, f"Курси з >= {min_enrollments} записів; порядок: {order}.")
    except Exception as exc:  # noqa: BLE001
        return _error(title, f"Не вдалося виконати запит: {type(exc).__name__}")


def get_completion_by_dimension(dimension: str = "level", min_enrollments: int = 30) -> dict:
    """Completion rate у розрізі виміру курсу.
    dimension: 'level' (рівень), 'domain' (домен) або 'partner' (партнер).
    min_enrollments: мінімум записів у групі (типово 30)."""
    title = f"Completion rate за виміром {dimension}"
    if dimension not in DIMENSIONS:
        return _error(title, f"dimension має бути одним із: {', '.join(DIMENSIONS)}.")
    min_enrollments = _clamp(min_enrollments, 1, 100000, DEFAULT_MIN_N)
    col = DIMENSIONS[dimension]  # значення з yaml, перевірене на старті
    try:
        df = run_select(
            f"""
            SELECT {col} AS {dimension},
                   COUNT(*) AS enrollments,
                   SUM(CASE WHEN {COMPLETED} THEN 1 ELSE 0 END) AS completed
            FROM public.enrollments e
            JOIN public.dim_course c ON c.course_id = e.course_id
            GROUP BY {col}
            HAVING COUNT(*) >= :min_n
            """,
            {"min_n": min_enrollments},
        )
        if df.empty:
            return _error(title, f"Немає груп із кількістю записів >= {min_enrollments}.")
        df = _add_rate(df).sort_values(
            ["completion_rate_pct", "enrollments"], ascending=[False, False]
        ).reset_index(drop=True)
        return _pack(title, df, f"Групи з >= {min_enrollments} записів.")
    except Exception as exc:  # noqa: BLE001
        return _error(title, f"Не вдалося виконати запит: {type(exc).__name__}")


TOOLS = {
    "get_overview": get_overview,
    "get_funnel": get_funnel,
    "get_completion_by_course": get_completion_by_course,
    "get_completion_by_dimension": get_completion_by_dimension,
}
