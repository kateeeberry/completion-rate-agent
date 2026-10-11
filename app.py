"""Дашборд Streamlit: Completion rate навчальної платформи + агент, що відповідає на питання.

Запуск:  streamlit run app.py
Колір і шрифти лежать у CSS нижче (змінні --ink, --accent тощо) та в .streamlit/config.toml.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import agent
import tools

st.set_page_config(page_title="Completion Rate Agent", page_icon="🎓", layout="wide")

# ---------- стиль -------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root {
  --bg: #F3F6FA; --ink: #14213D; --muted: #566680; --rule: #D5DEEA;
  --accent: #0F7B6C; --bar: #3F5B85;
  --s1: #D5DFEC; --s2: #A9BDD6; --s3: #6F8FB8;
}
.stApp { background: var(--bg); color: var(--ink); font-family: 'IBM Plex Sans', system-ui, sans-serif; }
header[data-testid="stHeader"], footer { display: none; }
.stApp .block-container { max-width: 1080px; padding: 2.4rem 1.2rem 3rem; }
.stApp h1, .stApp h2, .stApp h3, .display {
  font-family: 'Bricolage Grotesque', 'IBM Plex Sans', system-ui, sans-serif; color: var(--ink); letter-spacing: -0.02em;
}
.stApp h3 { font-size: 1.35rem; font-weight: 700; margin: 2.4rem 0 .2rem; padding: 0; }
.wordmark { font: 700 1.05rem 'Bricolage Grotesque', system-ui, sans-serif; color: var(--accent); margin: 0 0 1.6rem; }
.hero { display: flex; align-items: baseline; gap: 1.4rem; flex-wrap: wrap; }
.hero-num { font: 700 clamp(4.2rem, 12vw, 7.5rem)/0.9 'Bricolage Grotesque', system-ui, sans-serif;
            letter-spacing: -0.04em; color: var(--accent); }
.stApp .hero-text { font: 500 clamp(1.15rem, 2.6vw, 1.6rem)/1.25 'Bricolage Grotesque', system-ui, sans-serif;
             max-width: 22ch; margin: 0; }
.stApp .figures { display: flex; gap: 2.6rem; flex-wrap: wrap; margin: 1.6rem 0 0; }
.fig b { display: block; font: 700 1.9rem/1.1 'Bricolage Grotesque', system-ui, sans-serif; }
.fig span { color: var(--muted); font-size: .92rem; }
.stApp .definition { color: var(--muted); font-size: .92rem; max-width: 72ch; margin: 1.6rem 0 0; line-height: 1.5; }
.stApp .note { color: var(--muted); font-size: .9rem; margin: .2rem 0 1rem; max-width: 70ch; line-height: 1.5; }
.funnel { display: flex; gap: 2px; height: 46px; margin: 1.1rem 0 .9rem; }
.funnel .seg { min-width: 6px; border-radius: 2px; }
.funnel .seg:last-child { border-radius: 2px 8px 8px 2px; }
.funnel .seg:first-child { border-radius: 8px 2px 2px 8px; }
.legend { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
.legend div { border-top: 3px solid var(--c); padding-top: .45rem; }
.legend b { display: block; font-weight: 600; }
.legend span { color: var(--muted); font-size: .92rem; }
.rank { display: grid; grid-template-columns: 1.6rem 1fr 38% 4.2rem; gap: .9rem; align-items: center;
        padding: .55rem 0; border-bottom: 1px solid var(--rule); }
.rank:last-child { border-bottom: 0; }
.rank .i { color: var(--muted); font-variant-numeric: tabular-nums; }
.rank .name { line-height: 1.25; }
.rank .name small { display: block; color: var(--muted); font-size: .82rem; margin-top: .15rem; }
.rank .track { height: 8px; background: var(--s1); border-radius: 4px; overflow: hidden; }
.rank .track i { display: block; height: 100%; background: var(--bar); border-radius: 4px; }
.rank .val { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
.chip { display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-size: .85rem;
        background: var(--s1); color: var(--ink); }
.chip.llm { background: var(--accent); color: #fff; }
.stApp div[data-testid="stForm"] { border: 0; padding: 0; background: transparent; }
.stApp .stButton button, .stApp .stFormSubmitButton button {
  border-radius: 999px; border: 1px solid var(--rule); background: #fff; color: var(--ink); font-size: .9rem; }
.stApp .stFormSubmitButton button { background: var(--accent); color: #fff; border-color: var(--accent); font-weight: 600; }
.stApp .stTextInput input { background: #fff; border: 1px solid var(--rule); border-radius: 10px; }
@media (max-width: 760px) {
  .legend { grid-template-columns: repeat(2, 1fr); }
  .rank { grid-template-columns: 1.4rem 1fr 3.8rem; }
  .rank .track { display: none; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------- дані (кеш 10 хв) -------------------------------------------------


@st.cache_data(ttl=600, show_spinner="Рахую показники...")
def load_overview() -> dict:
    return tools.get_overview()


@st.cache_data(ttl=600, show_spinner=False)
def load_funnel() -> dict:
    return tools.get_funnel()


@st.cache_data(ttl=600, show_spinner=False)
def load_levels() -> dict:
    return tools.get_completion_by_dimension("level", min_enrollments=1)


@st.cache_data(ttl=600, show_spinner=False)
def load_top_courses() -> dict:
    return tools.get_completion_by_course(top_n=10, min_enrollments=tools.DEFAULT_MIN_N, order="best")


def to_frame(result: dict) -> pd.DataFrame:
    return pd.DataFrame(result["rows"], columns=result["columns"])


def num(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def pct(x) -> str:
    return f"{float(x):.2f}".replace(".", ",") + "%"


# ---------- шапка і головне число --------------------------------------------

overview = load_overview()
if "error" in overview:
    st.markdown('<p class="wordmark">Completion Rate Agent</p>', unsafe_allow_html=True)
    st.error(
        "Не вдалося отримати дані з бази. Перевірте файл .env (DATABASE_URL) і підключення. "
        f"Деталі: {overview['error']}"
    )
    st.stop()

row = overview["rows"][0]

st.markdown('<h1 class="wordmark">Completion Rate Agent</h1>', unsafe_allow_html=True)
st.markdown(
    f"""
<div class="hero">
  <div class="hero-num">{pct(row['completion_rate_pct'])}</div>
  <p class="hero-text">записів на курси закінчуються сертифікатом: {num(row['completed'])} із {num(row['enrollments'])}</p>
</div>
<div class="figures">
  <div class="fig"><b>{num(row['enrollments'])}</b><span>записів на курси</span></div>
  <div class="fig"><b>{num(row['learners'])}</b><span>унікальних студентів</span></div>
</div>
<p class="definition">Завершений запис = є сертифікат. Навчальна база, лише читання.</p>
""",
    unsafe_allow_html=True,
)

with st.expander("Як рахуємо completion rate"):
    st.markdown(
        "- **Джерело:** навчальна база coursera_capstone, доступ лише для читання.\n"
        "- **Completed:** `funnel_state = 'certified'` (студент отримав сертифікат).\n"
        "- **Completion rate:** завершені записи / усі записи × 100. Рахуємо записи на курс, не студентів.\n"
        f"- **Контроль даних:** {num(row['completed_at_without_certificate'])} записів мають `completed_at`, "
        "але не мають сертифіката. За цим визначенням вони не завершені."
    )

# ---------- воронка ------------------------------------------------------------

st.markdown("### Де зупиняються записи")
st.markdown(
    '<p class="note">Етап — поточний стан запису (funnel_state), а не шлях, який він пройшов. '
    "Назви етапів такі, як у базі.</p>",
    unsafe_allow_html=True,
)
funnel = load_funnel()
if "error" in funnel:
    st.warning(funnel["error"])
else:
    colors = {"registered": "var(--s1)", "viewed": "var(--s2)", "explored": "var(--s3)", "certified": "var(--accent)"}
    segs, legend = [], []
    for r in funnel["rows"]:
        name = escape(str(r["funnel_state"]))
        c = colors.get(r["funnel_state"], "var(--s2)")
        label = f"{name}: {num(r['enrollments'])} ({pct(r['share_pct'])})"
        segs.append(f'<div class="seg" style="flex:{r["enrollments"]};background:{c}" title="{label}"></div>')
        legend.append(
            f'<div style="--c:{c}"><b>{name}</b><span>{num(r["enrollments"])} · {pct(r["share_pct"])}</span></div>'
        )
    st.markdown(
        f'<div class="funnel">{"".join(segs)}</div><div class="legend">{"".join(legend)}</div>',
        unsafe_allow_html=True,
    )

# ---------- рівні курсів ------------------------------------------------------

st.markdown("### Рівень курсу і сертифікат")
levels = load_levels()
if "error" in levels:
    st.warning(levels["error"])
else:
    df_l = to_frame(levels)
    overall = float(row["completion_rate_pct"])
    fig = go.Figure(
        go.Bar(
            x=df_l["completion_rate_pct"],
            y=df_l["level"],
            orientation="h",
            marker_color="#3F5B85",
            text=[pct(v) for v in df_l["completion_rate_pct"]],
            textposition="inside",
            insidetextanchor="end",
            textfont=dict(color="#FFFFFF", size=15),
            customdata=df_l[["enrollments", "completed"]].to_numpy(),
            hovertemplate="%{y}: %{x:.2f}%<br>записів: %{customdata[0]:,}<br>завершено: %{customdata[1]:,}<extra></extra>",
        )
    )
    fig.add_vline(
        x=overall, line_dash="dot", line_color="#566680",
        annotation_text=f"усі курси {pct(overall)}", annotation_position="top", annotation_font_color="#566680",
    )
    fig.update_layout(
        height=60 + 52 * len(df_l),
        margin=dict(l=0, r=10, t=34, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", color="#14213D", size=14),
        xaxis=dict(visible=False, range=[0, max(df_l["completion_rate_pct"].max(), overall) * 1.08]),
        yaxis=dict(autorange="reversed", showgrid=False, ticks="", tickfont=dict(size=15)),
        bargap=0.45,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with st.expander("Таблиця даних для графіка"):
        st.dataframe(df_l, hide_index=True, width="stretch")

# ---------- курси -------------------------------------------------------------

st.markdown("### Курси, які дочитують найчастіше")
st.markdown(
    f'<p class="note">Лише курси, на які записалося не менше {tools.DEFAULT_MIN_N} студентів: '
    "інакше «1 із 1» дає 100% і потрапляє в топ.</p>",
    unsafe_allow_html=True,
)
top = load_top_courses()
if "error" in top:
    st.warning(top["error"])
else:
    rows = top["rows"]
    scale = max(float(r["completion_rate_pct"]) for r in rows) or 1.0
    items = []
    for i, r in enumerate(rows, 1):
        w = 100 * float(r["completion_rate_pct"]) / scale
        items.append(
            f'<div class="rank"><span class="i">{i}</span>'
            f'<div class="name">{escape(str(r["course"]))}'
            f'<small>{escape(str(r["level"]))} · {num(r["enrollments"])} записів · {escape(str(r["course_id"]))}</small></div>'
            f'<div class="track"><i style="width:{w:.1f}%"></i></div>'
            f'<div class="val">{pct(r["completion_rate_pct"])}</div></div>'
        )
    st.markdown("".join(items), unsafe_allow_html=True)

# ---------- агент -------------------------------------------------------------

st.markdown("### Запитайте агента")
st.markdown(
    '<p class="note">Агент не пише SQL: він обирає один із готових запитів, бере цифри з бази й пояснює їх. '
    "Під відповіддю видно таблицю, на якій вона побудована.</p>",
    unsafe_allow_html=True,
)

EXAMPLES = [
    ("Воронка", "Покажи воронку"),
    ("Рівні курсів", "Який рівень курсів має найвищий completion rate?"),
    ("Слабкі курси", "Які курси мають найнижчий completion rate?"),
    ("Домени", "Completion rate по доменах"),
]


def pick(q: str) -> None:
    st.session_state["q"] = q
    st.session_state["go"] = True


cols = st.columns(len(EXAMPLES))
for col, (label, q) in zip(cols, EXAMPLES):
    col.button(label, on_click=pick, args=(q,), key=f"ex_{label}", width="stretch")

with st.form("ask", border=False):
    st.text_input("Ваше запитання", key="q", max_chars=agent.MAX_QUESTION_CHARS)
    submitted = st.form_submit_button("Запитати")

if submitted or st.session_state.pop("go", False):
    with st.spinner("Агент працює..."):
        result = agent.ask(st.session_state.get("q", ""))
    st.session_state["last"] = (st.session_state.get("q", ""), result)

if "last" in st.session_state:
    q, result = st.session_state["last"]
    llm = result.mode.startswith("gemini")
    st.markdown(
        f'<p class="note"><b>Запитання:</b> {escape(q)}</p>'
        f'<span class="chip {"llm" if llm else ""}">'
        f'{escape(result.mode.replace("gemini:", "Gemini · ")) if llm else "без LLM · " + escape(result.mode)}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(result.answer)
    if result.warning:
        st.warning(result.warning)
    for call in result.tool_calls:
        with st.expander(f"Дані, на яких побудовано відповідь: {call['name']}"):
            res = call["result"]
            if "error" in res:
                st.error(res["error"])
            else:
                st.dataframe(to_frame(res), hide_index=True, width="stretch")
                if res.get("note"):
                    st.caption(res["note"])

st.markdown(
    f'<p class="note" style="margin-top:2.6rem">Джерело: coursera_capstone (навчальна БД, лише читання). '
    f"Оновлено {datetime.now():%Y-%m-%d %H:%M}.</p>",
    unsafe_allow_html=True,
)
