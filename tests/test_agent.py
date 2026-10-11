import agent
import tools


def test_offline_mode_routes_and_answers(engine, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "off")
    res = agent.ask("Покажи воронку")
    assert res.mode == "off" and res.tool_calls[0]["name"] == "get_funnel"
    assert "certified" in res.answer

    res = agent.ask("Який рівень курсів має найвищий completion rate?")
    assert res.tool_calls[0]["name"] == "get_completion_by_dimension"
    assert res.tool_calls[0]["args"] == {"dimension": "level"}

    res = agent.ask("Які курси найгірші?")
    assert res.tool_calls[0]["args"] == {"order": "worst"}

    res = agent.ask("Скільки всього завершено?")
    assert res.tool_calls[0]["name"] == "get_overview"
    assert "%" in res.answer


def test_missing_key_falls_back(engine, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "on")
    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    monkeypatch.setenv("GEMINI_MODEL", "put_current_model_name_here")
    res = agent.ask("Загальні показники")
    assert res.mode == "fallback" and res.warning


def test_gemini_failure_falls_back_without_leaking_key(engine, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "on")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-123")
    monkeypatch.setenv("GEMINI_MODEL", "some-model")

    def boom(*a, **k):
        raise RuntimeError("503 high demand SECRET-KEY-123")

    monkeypatch.setattr(agent, "_ask_gemini", boom)
    res = agent.ask("Загальні показники")
    assert res.mode == "fallback"
    assert "SECRET-KEY-123" not in (res.warning or "") + res.answer


def test_empty_and_long_question(engine, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "off")
    assert agent.ask("   ").answer == "Введіть запитання."
    assert agent.ask("курс " * 1000).tool_calls  # обрізається до 500 символів, не падає


def test_tool_schemas_build_for_gemini():
    """Перевіряємо, що SDK зможе описати наші Python-функції як інструменти (без мережі)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key="test-not-a-real-key")
    calls = []
    for fn in tools.TOOLS.values():
        decl = types.FunctionDeclaration.from_callable(client=client, callable=agent._recording(fn, calls))
        assert decl.name == fn.__name__ and decl.description
