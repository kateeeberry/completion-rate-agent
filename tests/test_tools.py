import pytest

import tools
from conftest import COURSES, ENROLLMENTS


def expected_rate(rows):
    done = sum(1 for r in rows if r[3] == "certified")
    return done, len(rows), round(100 * done / len(rows), 2)


def test_overview_matches_independent_count(engine):
    r = tools.get_overview()["rows"][0]
    done, total, rate = expected_rate(ENROLLMENTS)
    assert (r["completed"], r["enrollments"], r["completion_rate_pct"]) == (done, total, rate)
    assert r["learners"] == len({e[1] for e in ENROLLMENTS})
    # completed_at без сертифіката: 3 записи у c1
    assert r["completed_at_without_certificate"] == 3


def test_funnel_counts_and_order(engine):
    rows = tools.get_funnel()["rows"]
    assert [r["funnel_state"] for r in rows] == ["registered", "viewed", "explored", "certified"]
    assert sum(r["enrollments"] for r in rows) == len(ENROLLMENTS)
    assert sum(r["share_pct"] for r in rows) == pytest.approx(100, abs=0.05)


def test_by_course_threshold_hides_small_courses(engine):
    rows = tools.get_completion_by_course(top_n=10, min_enrollments=30)["rows"]
    ids = [r["course_id"] for r in rows]
    assert "c3" not in ids  # 5 записів < 30: 100% не потрапляє в рейтинг
    by_id = {r["course_id"]: r for r in rows}
    for cid in ("c1", "c2"):
        sub = [e for e in ENROLLMENTS if e[2] == cid]
        done, total, rate = expected_rate(sub)
        assert (by_id[cid]["completed"], by_id[cid]["enrollments"], by_id[cid]["completion_rate_pct"]) == (done, total, rate)


def test_by_course_order_best_and_worst(engine):
    best = tools.get_completion_by_course(min_enrollments=1, order="best")["rows"]
    worst = tools.get_completion_by_course(min_enrollments=1, order="worst")["rows"]
    assert best[0]["course_id"] == "c3"  # 5/5
    assert worst[0]["completion_rate_pct"] <= worst[-1]["completion_rate_pct"]


def test_by_dimension_level(engine):
    rows = {r["level"]: r for r in tools.get_completion_by_dimension("level", min_enrollments=1)["rows"]}
    beg = [e for e in ENROLLMENTS if e[2] in ("c1", "c3")]
    done, total, rate = expected_rate(beg)
    assert (rows["Beginner"]["completed"], rows["Beginner"]["enrollments"]) == (done, total)
    assert rows["Beginner"]["completion_rate_pct"] == rate


def test_unknown_dimension_is_rejected_without_sql(engine):
    out = tools.get_completion_by_dimension("level; DROP TABLE public.enrollments")
    assert "error" in out


def test_bad_order_returns_error(engine):
    assert "error" in tools.get_completion_by_course(order="sideways")


def test_run_select_rejects_writes(engine):
    for sql in ("DELETE FROM public.enrollments", "SELECT 1; DROP TABLE public.enrollments",
                "UPDATE public.enrollments SET funnel_state='x'"):
        with pytest.raises(ValueError):
            tools.run_select(sql)


def test_data_not_changed_after_tools(engine):
    before = len(ENROLLMENTS)
    tools.get_overview(); tools.get_funnel(); tools.get_completion_by_course()
    from sqlalchemy import text
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM public.enrollments")).scalar() == before


def test_definition_comes_from_semantic_layer():
    assert "funnel_state = 'certified'" in tools.COMPLETED
    assert set(tools.DIMENSIONS) == {"level", "domain", "partner"}
