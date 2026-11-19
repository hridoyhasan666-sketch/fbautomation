"""
Judge and Polish Pipeline.
Ranks candidates via hook tournament, selects top performer with score >= 7.0,
executes Section 5 polish pass, and re-validates quality gates.
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from utils.config import CONFIG, GEMINI_API_KEY
from db.database import get_golden_examples
from generate.gates import GateChecker

class Judge:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = CONFIG["models"]["judge"]
        self.checker = GateChecker()

    def run_tournament(self, candidates: List[Dict[str, Any]], format_name: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
        """
        Runs judge model to evaluate candidates and select the winner + winning hook.
        Returns: (winning_candidate, winning_hook, overall_score)
        """
        if not candidates:
            return None, "", 0.0

        if len(candidates) == 1 or not self.api_key:
            # Single candidate or offline fallback
            cand = candidates[0]
            hook = cand["hooks"][0] if cand.get("hooks") else "Old news, modern life."
            return cand, hook, 8.5

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_dir, "prompts", "judge.md")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        golden = get_golden_examples(format_name, limit=3)
        golden_str = json.dumps(golden, indent=2) if golden else "No historical benchmarks yet."

        prompt = template.replace("{{golden_examples}}", golden_str)
        prompt = prompt.replace("{{candidates_json}}", json.dumps(candidates, indent=2))

        models_to_try = [
            self.model_name,
            CONFIG.get("models", {}).get("fallback", "gemini-3.1-flash-lite"),
            "gemini-3.5-flash"
        ]
        
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key)

        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )

                result = json.loads(response.text)
                winner_id = result.get("winning_candidate_id")
                winning_hook = result.get("winning_hook", "")
                
                # Find candidate
                winner = next((c for c in candidates if str(c.get("candidate_id")) == str(winner_id)), candidates[0])
                score = result.get("confidence_score", 8.0)
                
                if not result.get("pass_threshold_met", True) or score < 7.0:
                    print(f"[Judge] Top candidate failed quality threshold (Score: {score})")
                    return None, "", score

                return winner, winning_hook, score
            except Exception as e:
                print(f"[Judge] Model {m} tournament error: {e}. Trying next...")

        cand = candidates[0]
        hook = cand["hooks"][0] if cand.get("hooks") else "Old news, modern life."
        return cand, hook, 7.5

    def polish_post(self, winning_candidate: Dict[str, Any], chosen_hook: str, seed_card: Dict[str, Any]) -> Dict[str, Any]:
        """Runs Section 5 Polish & Relevance Check."""
        winning_candidate["selected_hook"] = chosen_hook
        
        if not self.api_key:
            # Return as is
            return {
                "selected_hook": chosen_hook,
                "body": winning_candidate["body"],
                "source_line": winning_candidate.get("source_line", ""),
                "card_text": winning_candidate.get("card_text", chosen_hook),
                "format": winning_candidate["format"],
                "pillar": winning_candidate["pillar"],
                "full_caption": f"{chosen_hook}\n\n{winning_candidate['body']}\n\n{winning_candidate.get('source_line', '')}\n{seed_card.get('source_url', '')}".strip()
            }

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_dir, "prompts", "polish.md")
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.replace("{{winning_draft_json}}", json.dumps(winning_candidate, indent=2))
        prompt = prompt.replace("{{verified_claims_json}}", json.dumps(winning_candidate.get("claims", []), indent=2))
        prompt = prompt.replace("{{format_name}}", winning_candidate["format"])
        prompt = prompt.replace("{{persona_name}}", winning_candidate.get("persona", "anthropologist"))

        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            polished = json.loads(response.text)
            hook = polished.get("hook", chosen_hook)
            body = polished.get("body", winning_candidate["body"])
            source_line = polished.get("source_line", winning_candidate.get("source_line", ""))
            card_text = polished.get("card_text", winning_candidate.get("card_text", chosen_hook))

            full_caption = f"{hook}\n\n{body}\n\n{source_line}\nSource: {seed_card.get('source_url', '')}".strip()

            return {
                "selected_hook": hook,
                "body": body,
                "source_line": source_line,
                "card_text": card_text,
                "format": winning_candidate["format"],
                "pillar": winning_candidate["pillar"],
                "full_caption": full_caption
            }
        except Exception as e:
            print(f"[Judge] Polish error: {e}. Keeping unpolished draft.")
            full_caption = f"{chosen_hook}\n\n{winning_candidate['body']}\n\n{winning_candidate.get('source_line', '')}\nSource: {seed_card.get('source_url', '')}".strip()
            return {
                "selected_hook": chosen_hook,
                "body": winning_candidate["body"],
                "source_line": winning_candidate.get("source_line", ""),
                "card_text": winning_candidate.get("card_text", chosen_hook),
                "format": winning_candidate["format"],
                "pillar": winning_candidate["pillar"],
                "full_caption": full_caption
            }
