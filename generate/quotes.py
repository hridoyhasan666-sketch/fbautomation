"""
"Guess the quote" posts: a public-domain quote on the card, a one-line guessing question in the caption.
No AI needed - quotes come from the checked library in data/quotes.yaml.
The answer is stored in source_line and shown only in the Telegram approval message.
"""

import os
import random
import uuid
from typing import Dict, Any, Optional, List
import yaml
from utils.config import CONFIG
from db.database import save_post, get_connection
from render.card import CardRenderer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_PATH = os.path.join(BASE_DIR, "data", "quotes.yaml")

QUESTIONS = {
    "writer": [
        "Can you guess the writer? ✍️",
        "Who wrote this? Guess in the comments 👇",
        "Can you name the writer behind these words?",
        "Guess the author 🤔",
    ],
    "book": [
        "Can you guess the book? 📖",
        "Which book is this line from? 👇",
        "Name the book 📚",
        "Guess the book this came from 🤔",
    ],
}


def load_quotes() -> List[Dict[str, Any]]:
    with open(QUOTES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("quotes", [])


def used_quote_ids() -> List[str]:
    """Quote ids already posted or queued, most recent first (rejected ones can be reused)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT topic FROM posts WHERE format = 'guess_quote' AND status != 'rejected' "
            "ORDER BY created_at DESC").fetchall()
    return [r["topic"] for r in rows]


def pick_quote() -> Dict[str, Any]:
    quotes = load_quotes()
    used = used_quote_ids()
    fresh = [q for q in quotes if q["id"] not in used]
    if fresh:
        return random.choice(fresh)
    # Every quote used: reuse the one posted longest ago.
    order = {qid: i for i, qid in enumerate(used)}
    return max(quotes, key=lambda q: order.get(q["id"], -1))


def build_caption(ask: str) -> str:
    tags = (CONFIG.get("quotes", {}).get("hashtags", {}).get(ask, [])
            + CONFIG.get("caption", {}).get("brand_hashtags", []))
    return f"{random.choice(QUESTIONS[ask])}\n\n{' '.join(tags)}"


def generate_quote_post(renderer: Optional[CardRenderer] = None) -> Dict[str, Any]:
    q = pick_quote()
    ask = q.get("ask") or random.choice(["writer", "book"])
    post_id = f"post-{uuid.uuid4().hex[:8]}"
    card_path = (renderer or CardRenderer()).render_quote_card(q["text"], ask, post_id)
    answer = f"{q['author']} — {q['book']} ({q['year']})"
    if q.get("note"):
        answer += f" · {q['note']}"
    record = {
        "post_id": post_id,
        "seed_id": "quotes",
        "candidate_id": q["id"],
        "format": "guess_quote",
        "pillar": "quotes",
        "topic": q["id"],
        "selected_hook": q["text"][:200],
        "body": q["text"],
        "source_line": answer,
        "full_caption": build_caption(ask),
        "card_image_path": card_path,
        "status": "pending_approval",
    }
    save_post(record)
    print(f"[Quotes] Created {post_id}: {q['id']} (ask={ask}).")
    return record
