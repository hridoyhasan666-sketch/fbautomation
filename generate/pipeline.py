"""
End-to-End Generation & Curation Pipeline.
Connects:
Seed Selection -> 3x Drafting -> Code & Citation Gates -> Judge Tournament -> Section 5 Polish -> Card Rendering -> Pending Post Queue.
"""

import uuid
from typing import Dict, Any, Optional
from utils.config import CONFIG
from db.database import (
    get_next_seed_for_format,
    mark_seed_used,
    save_post,
    add_hook_to_history,
    get_recent_hooks
)
from generate.draft import Drafter
from generate.gates import GateChecker
from generate.judge import Judge
from render.card import CardRenderer

class StoryPipeline:
    def __init__(self):
        self.drafter = Drafter()
        self.checker = GateChecker()
        self.judge = Judge()
        self.renderer = CardRenderer()

    def generate_single_slot(self, format_name: str) -> Optional[Dict[str, Any]]:
        """Executes the full pipeline for one post slot."""
        print(f"\n[Pipeline] === Starting generation for format: {format_name} ===")
        
        # 1. Fetch seed card
        seed = get_next_seed_for_format(format_name)
        if not seed:
            print(f"[Pipeline] No new seeds available for format '{format_name}'. Run harvest first.")
            return None

        print(f"[Pipeline] Loaded seed {seed['seed_id']}: '{seed.get('place')}' ({seed.get('date')})")

        # 2. Draft 3 candidates with 5 hooks each
        raw_candidates = self.drafter.generate_candidates(seed)
        print(f"[Pipeline] Generated {len(raw_candidates)} candidate drafts.")

        # 3. Filter through Code & Citation Gates
        recent_hooks = get_recent_hooks(limit=60)
        surviving_candidates = []
        
        for cand in raw_candidates:
            passed, reason = self.checker.evaluate_candidate(cand, seed, recent_hooks)
            if passed:
                surviving_candidates.append(cand)
                print(f"[Pipeline] Candidate {cand.get('candidate_id')} PASSED all quality & citation gates.")
            else:
                print(f"[Pipeline] Candidate {cand.get('candidate_id')} REJECTED by gate: {reason}")

        if not surviving_candidates:
            print("[Pipeline] No candidates survived quality gates. Retrying or discarding seed.")
            return None

        # 4. Judge Tournament
        winner, chosen_hook, score = self.judge.run_tournament(surviving_candidates, format_name)
        if not winner:
            print(f"[Pipeline] No candidate passed Judge tournament with score >= 7.0.")
            return None

        print(f"[Pipeline] Winning draft selected (Score: {score}/10): '{chosen_hook}'")

        # 5. Section 5 Polish Pass
        polished = self.judge.polish_post(winner, chosen_hook, seed)

        # Re-verify polished post with gates to prevent hallucinated details
        recheck_cand = {
            "format": format_name,
            "body": polished["body"],
            "hooks": [polished["selected_hook"]],
            "claims": winner.get("claims", [])
        }
        re_ok, re_msg = self.checker.evaluate_candidate(recheck_cand, seed, recent_hooks)
        if not re_ok:
            print(f"[Pipeline] Warning: Polish pass triggered gate rejection ({re_msg}). Reverting to pre-polish.")
            final_hook = chosen_hook
            final_body = winner["body"]
            final_source = winner.get("source_line", "")
            final_card_text = winner.get("card_text", chosen_hook)
            full_caption = f"{chosen_hook}\n\n{winner['body']}\n\n{final_source}\nSource: {seed.get('source_url', '')}".strip()
        else:
            final_hook = polished["selected_hook"]
            final_body = polished["body"]
            final_source = polished.get("source_line", "")
            final_card_text = polished.get("card_text", final_hook)
            full_caption = polished["full_caption"]

        post_id = f"post-{uuid.uuid4().hex[:8]}"

        # 6. Render Story Card
        card_data = {
            "format": format_name,
            "selected_hook": final_hook,
            "card_text": final_card_text
        }
        card_path = self.renderer.render_card(card_data, seed, post_id)

        # 7. Save to Database
        post_record = {
            "post_id": post_id,
            "seed_id": seed["seed_id"],
            "candidate_id": winner.get("candidate_id"),
            "format": format_name,
            "pillar": seed["pillar"],
            "selected_hook": final_hook,
            "body": final_body,
            "source_line": final_source,
            "full_caption": full_caption,
            "card_image_path": card_path,
            "status": "pending_approval"
        }
        save_post(post_record)
        mark_seed_used(seed["seed_id"])
        add_hook_to_history(final_hook)

        print(f"[Pipeline] ✅ Successfully created {post_id} ready for Telegram approval!\n")
        return post_record

    def generate_batch(self, count_per_format: int = 1) -> int:
        """Generates a batch of posts across all configured formats."""
        created = 0
        for fmt in CONFIG["formats"]:
            for _ in range(count_per_format):
                res = self.generate_single_slot(fmt)
                if res:
                    created += 1
        return created
