"""
Code Quality Gates.
1. Length gate (word count per format)
2. Style gate (banned AI words, emojis, exclamation marks, links, hashtags in body)
3. Hook gate (length + not too similar to recent hooks)
4. Body must not repeat the hook
5. Format-specific rules (short_story fiction label)
Also builds the clean hashtag line appended to every caption.
"""

import re
import math
from typing import List, Dict, Any, Tuple
from utils.config import CONFIG

EMOJI_REGEX = re.compile(
    "[\U00010000-\U0010ffff"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B50-\U00002B55]",
    flags=re.UNICODE,
)
URL_REGEX = re.compile(r"(https?://|www\.)", re.IGNORECASE)
HASHTAG_IN_BODY = re.compile(r"(^|\s)#\w")
# Exact years ("1924") are usually invented; decades ("1920s") are fine.
EXACT_YEAR = re.compile(r"(?<!\d)1[6-9]\d\d(?![\ds])")

STORY_LABEL = "A short story inspired by everyday life a century ago."


def compute_text_similarity(text1: str, text2: str) -> float:
    """Character trigram cosine similarity."""
    def grams(t: str) -> Dict[str, int]:
        clean = re.sub(r"\s+", " ", t.lower().strip())
        counts: Dict[str, int] = {}
        for i in range(len(clean) - 2):
            g = clean[i:i + 3]
            counts[g] = counts.get(g, 0) + 1
        return counts

    v1, v2 = grams(text1), grams(text2)
    dot = sum(v1[k] * v2[k] for k in set(v1) & set(v2))
    m1 = math.sqrt(sum(c * c for c in v1.values()))
    m2 = math.sqrt(sum(c * c for c in v2.values()))
    return dot / (m1 * m2) if m1 and m2 else 0.0


def build_hashtags(model_tags: List[str]) -> List[str]:
    """Sanitises model hashtags, caps them, and appends brand tags. Deduplicates case-insensitively."""
    cap = CONFIG.get("caption", {})
    max_topic = cap.get("max_topic_hashtags", 5)
    out, seen = [], set()

    def add(tag: str):
        word = re.sub(r"[^A-Za-z0-9]", "", str(tag))
        if len(word) < 3 or word.isdigit():
            return
        key = word.lower()
        if key in seen:
            return
        seen.add(key)
        out.append("#" + word)

    for t in (model_tags or [])[: max_topic * 2]:
        if len(out) >= max_topic:
            break
        add(t)
    for t in cap.get("brand_hashtags", []):
        add(t)
    return out


def compose_caption(hook: str, body: str, hashtags: List[str]) -> str:
    parts = [hook.strip(), body.strip()]
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(p for p in parts if p)


class GateChecker:
    def __init__(self):
        g = CONFIG.get("gates", {})
        self.banned_words = [w.lower() for w in g.get("banned_words", [])]
        self.max_exclamation = g.get("max_exclamation_marks", 1)
        self.hook_max_words = g.get("hook_max_words", 15)
        self.repeat_threshold = g.get("hook_repeat_similarity_threshold", 0.80)

    def check_length(self, body: str, fmt: str) -> Tuple[bool, str]:
        words = len(body.split())
        f = CONFIG.get("formats", {}).get(fmt, {})
        lo, hi = f.get("min_words", 40), f.get("max_words", 300)
        if words < lo:
            return False, f"Body too short ({words} < {lo})"
        if words > hi:
            return False, f"Body too long ({words} > {hi})"
        return True, "ok"

    def check_style(self, text: str) -> Tuple[bool, str]:
        if EMOJI_REGEX.search(text):
            return False, "Contains emojis"
        if URL_REGEX.search(text):
            return False, "Contains a link"
        if EXACT_YEAR.search(text):
            return False, "Mentions an exact year (use a decade instead)"
        if text.count("!") > self.max_exclamation:
            return False, f"Too many exclamation marks ({text.count('!')})"
        lower = text.lower()
        for w in self.banned_words:
            if re.search(r"\b" + re.escape(w) + r"\b", lower):
                return False, f"Banned phrase: '{w}'"
        return True, "ok"

    def check_hook(self, hook: str, recent_hooks: List[str]) -> Tuple[bool, str]:
        if not hook.strip():
            return False, "Empty hook"
        if len(hook.split()) > self.hook_max_words:
            return False, "Hook too long"
        ok, msg = self.check_style(hook)
        if not ok:
            return False, msg
        for prev in recent_hooks:
            sim = compute_text_similarity(hook, prev)
            if sim >= self.repeat_threshold:
                return False, f"Hook too similar ({sim:.2f}) to '{prev}'"
        return True, "ok"

    def evaluate_candidate(self, cand: Dict[str, Any], recent_hooks: List[str]) -> Tuple[bool, str]:
        fmt = cand.get("format", "")
        body = (cand.get("body") or "").strip()

        ok, msg = self.check_length(body, fmt)
        if not ok:
            return False, f"[Length] {msg}"
        ok, msg = self.check_style(body)
        if not ok:
            return False, f"[Style] {msg}"
        if HASHTAG_IN_BODY.search(body):
            return False, "[Style] Hashtags inside body"
        if fmt == "short_story" and STORY_LABEL.lower() not in body.lower():
            return False, "[Format] short_story missing fiction label"

        valid_hooks = []
        for h in cand.get("hooks", []) or []:
            h = str(h).strip()
            if self.check_hook(h, recent_hooks)[0]:
                valid_hooks.append(h)
        if not valid_hooks:
            return False, "[Hook] All hooks failed length/style/repeat checks"

        first_sentence = re.split(r"(?<=[.!?])\s+|\n", body.strip(), maxsplit=1)[0].strip().lower()
        valid_hooks = [h for h in valid_hooks if compute_text_similarity(h, first_sentence) < 0.75]
        if not valid_hooks:
            return False, "[Hook] Body repeats the hook"

        cand["hooks"] = valid_hooks
        return True, "All gates passed"
