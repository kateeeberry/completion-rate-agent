"""Діагностика Gemini: перевіряє ключ і модель окремо від дашборда.

Запуск:  python check_gemini.py                  (модель із .env)
         python check_gemini.py gemini-3.5-flash-lite   (інша модель для порівняння)

Крок 1: простий запит без інструментів (чи приймає Google ключ і чи відповідає модель).
Крок 2: повний шлях агента з інструментами й базою (як у дашборді).
Ключ не друкується.
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()
key = (os.getenv("GEMINI_API_KEY") or "").strip()
model = sys.argv[1] if len(sys.argv) > 1 else (os.getenv("GEMINI_MODEL") or "").strip()

if not key or not model:
    sys.exit("Немає GEMINI_API_KEY або GEMINI_MODEL у .env")


def safe(text: str) -> str:
    return str(text).replace(key, "***")[:300]


print(f"Модель: {model}; довжина ключа: {len(key)}; початок ключа: {key[:3]}...")

from google import genai
from google.genai import types

client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=25_000))

print("\nКрок 1: простий запит без інструментів")
t = time.time()
try:
    r = client.models.generate_content(model=model, contents="Відповідай одним словом: 2+2=?")
    print(f"OK за {time.time() - t:.1f} с. Відповідь: {safe(r.text)}")
except Exception as exc:  # noqa: BLE001
    print(f"ПОМИЛКА за {time.time() - t:.1f} с: {type(exc).__name__}, код {getattr(exc, 'code', None)}: {safe(exc)}")
    sys.exit("Крок 1 не пройшов: проблема в ключі, моделі або лімітах, а не в коді проєкту.")

print("\nКрок 2: агент з інструментами і базою")
import agent  # noqa: E402

t = time.time()
try:
    res = agent._ask_gemini("Який рівень курсів має найвищий completion rate?", key, model)
    print(f"OK за {time.time() - t:.1f} с. Режим: {res.mode}; інструменти: {[c['name'] for c in res.tool_calls]}")
    print(res.answer)
except Exception as exc:  # noqa: BLE001
    print(f"ПОМИЛКА за {time.time() - t:.1f} с: {type(exc).__name__}, код {getattr(exc, 'code', None)}: {safe(exc)}")
