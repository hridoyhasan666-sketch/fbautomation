"""
Judge and Polish.
Scores surviving candidates, rejects everything below the minimum score,
then runs a light polish pass on the winner.
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from utils.config import CONFIG
from db.database import get_golden_examples
from generate.llm import call_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _template(name: str) -> str:
    with open(os.path.join(BASE_DIR, "prompts", name), "r", encoding="utf-8") as f:
        return f.read()


class Judge:
    def __init__(self):
        self.min_score = CONFIG.get("gates", {}).get("min_judge_score", 7.0)
        self.page_name = CONFIG.get("brand", {}).get("page_name", "")

    def run_tournament(self, candidates: List[Dict[str, Any]], format_name: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
        """Returns (winner, winning_hook, score) or (None, "", score) if nothing is good enough."""
        if not candidates:
            return None, "", 0.0

        golden = get_golden_examples(format_name, limit=3)
        golden_str = json.dumps([{"hook": g["hook"], "body": g["body"]} for g in golden], indent=2) if golden else "None yet."
        slim = [{k: c.get(k) for k in ("candidate_id", "hooks", "body")} for c in candidates]

        prompt = (_template("judge.md")
                  .replace("{{page_name}}", self.page_name)
                  .replace("{{golden_examples}}", golden_str)
                  .replace("{{candidates_json}}", json.dumps(slim, indent=2)))

        result = call_json(prompt, "judge", temperature=0.2)
        if not isinstance(result, dict):
            print("[Judge] Judge unavailable; refusing to pass unjudged content.")
            return None, "", 0.0

        winner_id = str(result.get("winning_candidate_id"))
        winner = next((c for c in candidates if str(c.get("candidate_id")) == winner_id), None)
        try:
            score = float(result.get("confidence_score", 0))
        except (TypeError, ValueError):
            score = 0.0

        for ev in result.get("evaluations", []):
            print(f"[Judge] Candidate {ev.get('candidate_id')}: {ev.get('overall_average')} - {ev.get('critique')}")

        if winner is None or score < self.min_score:
            print(f"[Judge] No candidate reached {self.min_score} (best: {score}).")
            return None, "", score

        hook = result.get("winning_hook") or ""
        if hook not in winner["hooks"]:
            hook = winner["hooks"][0]
        return winner, hook, score

    def polish_post(self, winner: Dict[str, Any], hook: str) -> Dict[str, str]:
        """Returns dict with hook/body/card_text. Falls back to the unpolished winner on failure."""
        fmt = winner["format"]
        f_cfg = CONFIG["formats"].get(fmt, {})
        extra = ""
        if fmt == "short_story":
            extra = '9. The body\'s last line must stay exactly: "A short story inspired by everyday life a century ago."'

        prompt = (_template("polish.md")
                  .replace("{{page_name}}", self.page_name)
                  .replace("{{min_words}}", str(f_cfg.get("min_words", 40)))
                  .replace("{{max_words}}", str(f_cfg.get("max_words", 300)))
                  .replace("{{extra_rule}}", extra)
                  .replace("{{hook}}", hook)
                  .replace("{{body}}", winner["body"])
                  .replace("{{card_text}}", winner.get("card_text") or hook))

        original = {"hook": hook, "body": winner["body"], "card_text": winner.get("card_text") or hook}
        polished = call_json(prompt, "judge", temperature=0.3)
        if not isinstance(polished, dict) or not polished.get("body"):
            return original
        return {
            "hook": (polished.get("hook") or hook).strip(),
            "body": polished["body"].strip(),
            "card_text": (polished.get("card_text") or original["card_text"]).strip(),
        }
