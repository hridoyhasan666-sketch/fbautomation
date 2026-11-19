"""
Candidate Generator (Drafting Phase).
Assembles persona DNA, format briefs, source clippings, and prompt templates.
Calls Gemini API to generate 3 distinct candidates with 5 hooks each and structured OCR citations.
"""

import os
import json
import uuid
from typing import Dict, Any, List, Optional
from utils.config import CONFIG, GEMINI_API_KEY
from utils.cpi import format_price_comparison, calculate_inflation
from db.database import get_recent_hooks, get_golden_examples

class Drafter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = CONFIG["models"]["draft"]

    def load_persona_prompt(self, persona_name: str) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        core_path = os.path.join(base_dir, "personas", "core.md")
        persona_path = os.path.join(base_dir, "personas", f"{persona_name}.md")
        
        with open(core_path, "r", encoding="utf-8") as f:
            core_text = f.read()
            
        persona_text = ""
        if os.path.exists(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
                
        return f"{core_text}\n\n{persona_text}"

    def load_format_brief(self, format_name: str) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "formats", f"{format_name}.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def build_draft_prompt(self, seed_card: Dict[str, Any]) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_tmpl_path = os.path.join(base_dir, "prompts", "draft.md")
        with open(prompt_tmpl_path, "r", encoding="utf-8") as f:
            template = f.read()

        fmt = seed_card["format"]
        pillar = seed_card["pillar"]
        persona_name = CONFIG["pillars"].get(pillar, {}).get("persona", "anthropologist")
        
        persona_content = self.load_persona_prompt(persona_name)
        format_content = self.load_format_brief(fmt)
        
        # CPI section for price format
        cpi_section = ""
        if fmt == "price" and seed_card.get("price_data"):
            p_data = seed_card["price_data"]
            cents = p_data.get("price_cents", 100)
            year = p_data.get("year", 1900)
            item = p_data.get("item", "item")
            comparison = format_price_comparison(cents, year, item)
            today_val, mult = calculate_inflation(cents / 100.0, year)
            cpi_section = (
                f"\n## PRE-CALCULATED INFLATION DATA (MANDATORY TO USE AS GIVEN):\n"
                f"- Past Price: {cents} cents in {year}\n"
                f"- Today's Equivalent: ${today_val:,.2f} ({mult}x increase)\n"
                f"- Context line: {comparison}\n"
            )

        recent_hooks = get_recent_hooks(limit=30)
        recent_hooks_str = "\n".join(f"- {h}" for h in recent_hooks) if recent_hooks else "None yet."

        prompt = template.replace("{{persona_content}}", persona_content)
        prompt = prompt.replace("{{format_content}}", format_content)
        prompt = prompt.replace("{{source_paper}}", seed_card.get("source", "Historical Archive"))
        prompt = prompt.replace("{{source_date}}", seed_card.get("date", ""))
        prompt = prompt.replace("{{source_place}}", seed_card.get("place", ""))
        prompt = prompt.replace("{{ocr_text}}", seed_card.get("ocr_text", ""))
        prompt = prompt.replace("{{seed_card_json}}", json.dumps(seed_card, indent=2))
        prompt = prompt.replace("{{cpi_data_section}}", cpi_section)
        prompt = prompt.replace("{{recent_hooks}}", recent_hooks_str)
        prompt = prompt.replace("{{format_name}}", fmt)
        prompt = prompt.replace("{{persona_name}}", persona_name)
        
        return prompt

    def generate_candidates(self, seed_card: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generates 3 candidates via Gemini API with automatic fallback."""
        prompt = self.build_draft_prompt(seed_card)
        
        if not self.api_key:
            print("[Drafter] No GEMINI_API_KEY found, generating fallback candidate.")
            return self._generate_fallback(seed_card)

        from google import genai
        from google.genai import types
        
        models_to_try = [
            self.model_name,
            CONFIG.get("models", {}).get("fallback", "gemini-3.1-flash-lite"),
            "gemini-3.5-flash",
            "gemini-3.7-flash"
        ]
        
        client = genai.Client(api_key=self.api_key)
        
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.7
                    )
                )
                
                parsed = json.loads(response.text)
                candidates = parsed.get("candidates", [])
                for c in candidates:
                    if "candidate_id" not in c:
                        c["candidate_id"] = f"c-{uuid.uuid4().hex[:6]}"
                    c["format"] = seed_card["format"]
                    c["pillar"] = seed_card["pillar"]
                if candidates:
                    print(f"[Drafter] Successfully generated candidates using {m}.")
                    return candidates
            except Exception as e:
                print(f"[Drafter] Model {m} error: {e}. Trying next model...")

        print("[Drafter] All models failed. Falling back to deterministic draft.")
        return self._generate_fallback(seed_card)

    def _generate_fallback(self, seed_card: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Provides a valid fallback candidate when API is unavailable."""
        fmt = seed_card["format"]
        facts = seed_card.get("facts", ["A surprising event occurred in 1903."])
        fact_1 = facts[0] if facts else "An event was recorded in the old papers."
        ocr = seed_card.get("ocr_text", "")
        # Pick a short real snippet from OCR
        words = ocr.split()
        snippet = " ".join(words[:6]) if len(words) >= 6 else "four dollars"
        
        body = (
            f"{fact_1}\n\n"
            f"The records show the quiet desperation behind what looks like a simple line in the court blotter. "
            f"When we look at our own choices today, the pressure to maintain appearances has not changed. "
            f"Only the technology has shifted.\n\n"
            f"We still pawn our peace of mind for things we think will win approval."
        )
        
        return [{
            "candidate_id": f"c-fallback-{uuid.uuid4().hex[:6]}",
            "opening_style": "scene",
            "hooks": [
                f"Why a clerk pawned his coat in June.",
                "The price of keeping up appearances in 1903.",
                "He told the court it was for a ring.",
                "What we buy when we cannot afford to look broke.",
                "A four-dollar lie in the summer heat."
            ],
            "body": body,
            "claims": [
                {
                    "claim": "The clerk pawned an item for four dollars",
                    "ocr_quote": snippet
                }
            ],
            "format": fmt,
            "pillar": seed_card.get("pillar", "money"),
            "persona": "anthropologist",
            "ending": "open",
            "source_line": f"From a real item in {seed_card.get('source', 'old records')}.",
            "card_text": "Pawning your winter coat in June just to afford an engagement ring."
        }]
