"""
Code Quality Gates and Citation Verifier.
Implements:
1. Length Gate (word count per format)
2. Banned Words & AI Cliché Gate
3. Emoji & Exclamation Mark Gate
4. Hook Repeat & Cosine Similarity Gate
5. Citation Gate (>=90% fuzzy match against OCR text)
6. Number & Year Guard
"""

import re
import math
import json
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple
from utils.config import CONFIG
from db.database import get_recent_hooks

# Regex for detecting any unicode emoji
EMOJI_REGEX = re.compile(
    "[\U00010000-\U0010ffff"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B50-\U00002B55"
    "\U0001F300-\U0001F64F"
    "\U0001F680-\U0001F6FF]",
    flags=re.UNICODE
)

def normalize_text_for_ocr(text: str) -> str:
    """Normalizes noisy OCR text and candidate quotes for comparison."""
    if not text:
        return ""
    text = text.lower()
    # Normalize common OCR transcription swaps
    text = text.replace("rn", "m")
    text = text.replace("vv", "w")
    text = text.replace("—", " ").replace("–", " ").replace("-", " ")
    # Strip punctuation and collapse whitespace
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def calculate_fuzzy_match(sub_str: str, full_str: str) -> float:
    """
    Finds best matching substring in full_str and returns SequenceMatcher ratio.
    """
    sub_norm = normalize_text_for_ocr(sub_str)
    full_norm = normalize_text_for_ocr(full_str)
    
    if not sub_norm:
        return 1.0
    if sub_norm in full_norm:
        return 1.0
        
    sub_len = len(sub_norm)
    words = full_norm.split()
    sub_words = sub_norm.split()
    n_words = len(sub_words)
    
    best_ratio = 0.0
    # Sliding window of word tokens
    for i in range(max(1, len(words) - n_words + 1)):
        window = " ".join(words[i:i + n_words + 2])
        ratio = SequenceMatcher(None, sub_norm, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
        if best_ratio >= 0.95:
            return 1.0
            
    return best_ratio

def compute_text_similarity(text1: str, text2: str) -> float:
    """Computes character n-gram cosine similarity between two hooks."""
    def get_ngrams(t: str, n: int = 3) -> Dict[str, int]:
        clean = re.sub(r"\s+", " ", t.lower().strip())
        counts = {}
        for i in range(len(clean) - n + 1):
            gram = clean[i:i+n]
            counts[gram] = counts.get(gram, 0) + 1
        return counts

    v1 = get_ngrams(text1)
    v2 = get_ngrams(text2)
    
    intersection = set(v1.keys()) & set(v2.keys())
    dot = sum(v1[k] * v2[k] for k in intersection)
    mag1 = math.sqrt(sum(c * c for c in v1.values()))
    mag2 = math.sqrt(sum(c * c for c in v2.values()))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

class GateChecker:
    def __init__(self):
        self.banned_words = [w.lower() for w in CONFIG.get("gates", {}).get("banned_words", [])]
        self.max_exclamation = CONFIG.get("gates", {}).get("max_exclamation_marks", 2)
        self.hook_max_words = CONFIG.get("gates", {}).get("hook_max_words", 15)
        self.repeat_threshold = CONFIG.get("gates", {}).get("hook_repeat_similarity_threshold", 0.85)
        self.citation_threshold = CONFIG.get("gates", {}).get("citation_fuzzy_threshold", 0.90)

    def check_length(self, body_text: str, format_name: str) -> Tuple[bool, str]:
        words = len(body_text.split())
        f_cfg = CONFIG.get("formats", {}).get(format_name, {})
        min_words = f_cfg.get("min_words", 40)
        max_words = f_cfg.get("max_words", 300)
        
        if words < min_words:
            return False, f"Body too short ({words} words < min {min_words})"
        if words > max_words:
            return False, f"Body too long ({words} words > max {max_words})"
        return True, "Passed"

    def check_banned_words_and_style(self, text: str) -> Tuple[bool, str]:
        # Check emojis
        if EMOJI_REGEX.search(text):
            return False, "Contains emojis (banned in style guide)"
            
        # Check exclamation marks
        if text.count("!") > self.max_exclamation:
            return False, f"Too many exclamation marks ({text.count('!')} > {self.max_exclamation})"
            
        # Check banned words
        lower_text = text.lower()
        for word in self.banned_words:
            # Word boundary check
            if re.search(r"\b" + re.escape(word) + r"\b", lower_text):
                return False, f"Contains banned AI word: '{word}'"
                
        return True, "Passed"

    def check_hook_repeats(self, hook: str, recent_hooks: List[str]) -> Tuple[bool, str]:
        words = len(hook.split())
        if words > self.hook_max_words:
            return False, f"Hook exceeds maximum {self.hook_max_words} words ({words} words)"
            
        for prev in recent_hooks:
            sim = compute_text_similarity(hook, prev)
            if sim >= self.repeat_threshold:
                return False, f"Hook too similar ({sim:.2f} >= {self.repeat_threshold}) to previous: '{prev}'"
                
        return True, "Passed"

    def check_citation_gate(self, claims: List[Dict[str, str]], ocr_text: str, format_name: str) -> Tuple[bool, str]:
        # Story Sunday is labeled fiction and exempt from OCR citation gate
        if format_name == "story_sunday":
            return True, "Story Sunday is exempt from citation gate"
            
        if not claims:
            return False, "No citation claims provided for factual format"
            
        for item in claims:
            ocr_quote = item.get("ocr_quote", "")
            if not ocr_quote or len(ocr_quote.strip()) < 5:
                return False, f"Empty or trivial OCR quote for claim: {item.get('claim')}"
                
            match_score = calculate_fuzzy_match(ocr_quote, ocr_text)
            if match_score < self.citation_threshold:
                return False, f"Citation mismatch ({match_score:.2f} < {self.citation_threshold}) for: '{ocr_quote}'"
                
        return True, "Citation gate verified"

    def check_number_guard(self, body_text: str, seed_card: Dict[str, Any], ocr_text: str) -> Tuple[bool, str]:
        """Ensures 4-digit years or prices in body appear in seed facts or OCR."""
        # Find 4-digit years (1800-1930)
        years_in_body = set(re.findall(r"\b(18\d\d|19[0-2]\d|1930)\b", body_text))
        combined_source = (ocr_text + " " + json.dumps(seed_card.get("facts", [])) + " " + seed_card.get("date", "")).lower()
        
        for y in years_in_body:
            if y not in combined_source:
                return False, f"Unverified year mentioned in body: {y}"
                
        return True, "Number guard passed"

    def evaluate_candidate(self, candidate: Dict[str, Any], seed_card: Dict[str, Any], recent_hooks: List[str]) -> Tuple[bool, str]:
        """Runs all code gates on a candidate draft."""
        fmt = candidate.get("format", seed_card.get("format"))
        body = candidate.get("body", "")
        ocr_text = seed_card.get("ocr_text", "")
        
        # 1. Length
        ok, msg = self.check_length(body, fmt)
        if not ok:
            return False, f"[Length Gate] {msg}"
            
        # 2. Banned words and style
        ok, msg = self.check_banned_words_and_style(body)
        if not ok:
            return False, f"[Style Gate] {msg}"
            
        # 3. Citation Gate
        ok, msg = self.check_citation_gate(candidate.get("claims", []), ocr_text, fmt)
        if not ok:
            return False, f"[Citation Gate] {msg}"
            
        # 4. Number guard
        ok, msg = self.check_number_guard(body, seed_card, ocr_text)
        if not ok:
            return False, f"[Number Guard] {msg}"
            
        # 5. Hooks validation
        hooks = candidate.get("hooks", [])
        if not hooks:
            return False, "[Hook Gate] No hooks provided"
            
        valid_hooks = []
        for h in hooks:
            h_ok, h_msg = self.check_banned_words_and_style(h)
            if not h_ok:
                continue
            r_ok, r_msg = self.check_hook_repeats(h, recent_hooks)
            if not r_ok:
                continue
            valid_hooks.append(h)
            
        if not valid_hooks:
            return False, "[Hook Gate] All hooks failed length, style, or repeat checks"
            
        candidate["hooks"] = valid_hooks
        return True, "All gates passed"
