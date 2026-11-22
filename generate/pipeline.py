"""
End-to-End Generation Pipeline.
Pick format + fresh topic -> 3 drafts -> code gates -> judge -> polish -> re-gate -> card -> approval queue.
"""

import random
import uuid
from typing import Dict, Any, Optional, Tuple
from utils.config import CONFIG
from db.database import save_post, add_hook_to_history, get_recent_hooks, get_recent_topics, get_bandit_weights
from generate.draft import Drafter
from generate.gates import GateChecker, build_hashtags, compose_caption
from generate.judge import Judge
from render.card import CardRenderer


class StoryPipeline:
    def __init__(self):
        self.drafter = Drafter()
        self.checker = GateChecker()
        self.judge = Judge()
        self.renderer = CardRenderer()

    def pick_format(self) -> str:
        formats = CONFIG["formats"]
        learned = get_bandit_weights()
        weights = [learned.get(f, formats[f].get("initial_weight", 0.1)) for f in formats]
        return random.choices(list(formats), weights=weights, k=1)[0]

    def pick_topic(self) -> Tuple[str, str]:
        cooldown = CONFIG.get("generation", {}).get("topic_cooldown_posts", 40)
        recent = set(get_recent_topics(limit=cooldown))
        all_topics = [(p, t) for p, cfg in CONFIG["pillars"].items() for t in cfg.get("topics", [])]
        fresh = [pt for pt in all_topics if pt[1] not in recent]
        return random.choice(fresh or all_topics)

    def generate_single_slot(self, format_name: Optional[str] = None, max_attempts: int = 3) -> Optional[Dict[str, Any]]:
        for attempt in range(1, max_attempts + 1):
            fmt = format_name or self.pick_format()
            pillar, topic = self.pick_topic()
            print(f"\n[Pipeline] Attempt {attempt}: format={fmt} pillar={pillar} topic='{topic}'")
            post = self._run(fmt, pillar, topic)
            if post:
                return post
        print("[Pipeline] Gave up on this slot after all attempts.")
        return None

    def _run(self, fmt: str, pillar: str, topic: str) -> Optional[Dict[str, Any]]:
        slot = {"format": fmt, "pillar": pillar, "topic": topic}
        candidates = self.drafter.generate_candidates(slot)
        if not candidates:
            print("[Pipeline] Drafting failed.")
            return None

        recent_hooks = get_recent_hooks(limit=60)
        survivors = []
        for c in candidates:
            ok, reason = self.checker.evaluate_candidate(c, recent_hooks)
            print(f"[Pipeline] Candidate {c.get('candidate_id')}: {'PASS' if ok else 'REJECT ' + reason}")
            if ok:
                survivors.append(c)
        if not survivors:
            return None

        winner, hook, score = self.judge.run_tournament(survivors, fmt)
        if not winner:
            return None
        print(f"[Pipeline] Winner (score {score}): '{hook}'")

        polished = self.judge.polish_post(winner, hook)
        recheck = {"format": fmt, "body": polished["body"], "hooks": [polished["hook"]]}
        if self.checker.evaluate_candidate(recheck, recent_hooks)[0]:
            final = polished
        else:
            print("[Pipeline] Polished version failed gates; using the judged draft.")
            final = {"hook": hook, "body": winner["body"], "card_text": winner.get("card_text") or hook}

        hashtags = build_hashtags(winner.get("hashtags", []))
        caption = compose_caption(final["hook"], final["body"], hashtags)

        post_id = f"post-{uuid.uuid4().hex[:8]}"
        card_path = self.renderer.render_card(
            {"format": fmt, "selected_hook": final["hook"], "card_text": final["card_text"]}, post_id
        )

        record = {
            "post_id": post_id,
            "seed_id": f"topic:{pillar}",
            "candidate_id": str(winner.get("candidate_id")),
            "format": fmt,
            "pillar": pillar,
            "topic": topic,
            "selected_hook": final["hook"],
            "body": final["body"],
            "source_line": "",
            "full_caption": caption,
            "card_image_path": card_path,
            "status": "pending_approval",
        }
        save_post(record)
        add_hook_to_history(final["hook"])
        print(f"[Pipeline] Created {post_id}, waiting for Telegram approval.")
        return record

    def generate_batch(self, count: int) -> int:
        return sum(1 for _ in range(count) if self.generate_single_slot())
