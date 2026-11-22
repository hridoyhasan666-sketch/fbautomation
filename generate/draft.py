"""
Candidate Generator (Drafting Phase).
Builds a prompt from persona + format brief + topic, and asks Gemini for 3 candidates.
If Gemini fails, returns no candidates (we never publish canned filler text).
"""

import os
import uuid
from typing import Dict, Any, List
from utils.config import CONFIG
from db.database import get_recent_hooks
from generate.llm import call_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts: str) -> str:
    path = os.path.join(BASE_DIR, *parts)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


class Drafter:
    def build_draft_prompt(self, slot: Dict[str, Any]) -> str:
        fmt, pillar, topic = slot["format"], slot["pillar"], slot["topic"]
        persona_name = CONFIG["pillars"].get(pillar, {}).get("persona", "anthropologist")
        persona = _read("personas", "core.md") + "\n\n" + _read("personas", f"{persona_name}.md")
        brand = CONFIG.get("brand", {})
        cap = CONFIG.get("caption", {})

        recent = get_recent_hooks(limit=30)
        recent_str = "\n".join(f"- {h}" for h in recent) if recent else "None yet."

        replacements = {
            "{{page_name}}": brand.get("page_name", ""),
            "{{tagline}}": brand.get("tagline", ""),
            "{{persona_content}}": persona,
            "{{format_content}}": _read("formats", f"{fmt}.md"),
            "{{topic}}": topic,
            "{{pillar}}": pillar,
            "{{recent_hooks}}": recent_str,
            "{{min_tags}}": str(cap.get("min_topic_hashtags", 3)),
            "{{max_tags}}": str(cap.get("max_topic_hashtags", 5)),
        }
        prompt = _read("prompts", "draft.md")
        for k, v in replacements.items():
            prompt = prompt.replace(k, v)
        return prompt

    def generate_candidates(self, slot: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed = call_json(self.build_draft_prompt(slot), "draft", temperature=0.8)
        if not isinstance(parsed, dict):
            return []
        persona = CONFIG["pillars"].get(slot["pillar"], {}).get("persona", "anthropologist")
        candidates = [c for c in parsed.get("candidates", []) if isinstance(c, dict) and c.get("body")]
        for c in candidates:
            c.setdefault("candidate_id", f"c-{uuid.uuid4().hex[:6]}")
            c["format"] = slot["format"]
            c["pillar"] = slot["pillar"]
            c["persona"] = persona
        return candidates
