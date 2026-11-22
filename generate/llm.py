"""
Shared Gemini JSON caller with model fallback.
Returns parsed JSON or None. Never fabricates content when every model fails.
"""

import json
import time
from typing import Any, Optional
from utils.config import CONFIG, GEMINI_API_KEY


def model_chain(primary_key: str) -> list:
    models = CONFIG.get("models", {})
    chain = [models.get(primary_key), models.get("fallback"), models.get("last_resort", "gemini-3.8-flash")]
    seen, out = set(), []
    for m in chain:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def call_json(prompt: str, primary_key: str = "draft", temperature: float = 0.7) -> Optional[Any]:
    if not GEMINI_API_KEY:
        print("[LLM] GEMINI_API_KEY missing.")
        return None

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    for m in model_chain(primary_key):
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=temperature,
                    ),
                )
                return json.loads(resp.text)
            except Exception as e:
                busy = "503" in str(e) or "UNAVAILABLE" in str(e) or "429" in str(e)
                print(f"[LLM] Model {m} failed (attempt {attempt + 1}): {str(e)[:160]}")
                if not busy:
                    break  # wrong model name / bad request: retrying won't help
                time.sleep(8 * (attempt + 1))
    print("[LLM] All models failed.")
    return None
