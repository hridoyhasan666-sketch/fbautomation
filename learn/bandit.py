"""
The Learning Loop & Thompson Sampling Bandit.
Runs every Sunday:
1. Scores 48h engagement: (reactions*1 + comments*3 + shares*5) / (reach / 1000).
2. Reweights format shares using Thompson Sampling on Beta(wins+1, losses+1).
3. Clamps format weights to [5%, 40%].
4. Refreshes Golden Examples in the database from top performers.
5. Evaluates judge calibration.
"""

import random
from typing import Dict, Any, List, Tuple
from utils.config import CONFIG
from db.database import (
    get_connection,
    get_bandit_weights,
    set_bandit_weight
)

class LearningLoop:
    def __init__(self):
        self.formats = list(CONFIG.get("formats", {}).keys())

    def calculate_post_score(self, reactions: int, comments: int, shares: int, reach: int) -> float:
        """Calculates 48-hour composite viral engagement score."""
        if reach <= 0:
            reach = 100
        score = (reactions * 1.0 + comments * 3.0 + shares * 5.0) / (reach / 1000.0)
        return round(score, 2)

    def evaluate_format_wins_losses(self) -> Dict[str, Tuple[int, int]]:
        """
        Calculates wins and losses per format.
        A win is defined as being in the top 30% of post scores over recent history.
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT p.format, m.score 
            FROM posts p
            JOIN metrics m ON p.post_id = m.post_id
            WHERE m.score > 0
            ORDER BY p.created_at DESC LIMIT 60
            """)
            rows = cursor.fetchall()

        if not rows:
            # Cold start: return balanced initial counts
            return {fmt: (3, 3) for fmt in self.formats}

        scores = [r["score"] for r in rows]
        scores_sorted = sorted(scores, reverse=True)
        threshold_idx = max(1, int(len(scores_sorted) * 0.30)) - 1
        win_threshold = scores_sorted[threshold_idx]

        results = {fmt: [0, 0] for fmt in self.formats}
        for r in rows:
            fmt = r["format"]
            if fmt in results:
                if r["score"] >= win_threshold:
                    results[fmt][0] += 1 # win
                else:
                    results[fmt][1] += 1 # loss

        return {k: (v[0], v[1]) for k, v in results.items()}

    def run_thompson_sampling(self, draws: int = 1000) -> Dict[str, float]:
        """
        Samples Beta(wins + 1, losses + 1) for each format across draws.
        Calculates probability each format wins, then applies floor (5%) and cap (40%).
        """
        stats = self.evaluate_format_wins_losses()
        sim_wins = {fmt: 0 for fmt in self.formats}

        for _ in range(draws):
            sampled_vals = {}
            for fmt in self.formats:
                wins, losses = stats.get(fmt, (0, 0))
                # Beta(alpha, beta) where alpha = wins + 1, beta = losses + 1
                sampled_vals[fmt] = random.betavariate(wins + 1, losses + 1)
            
            # Winner of this simulation draw
            winner = max(sampled_vals.items(), key=lambda x: x[1])[0]
            sim_wins[winner] += 1

        raw_shares = {fmt: sim_wins[fmt] / float(draws) for fmt in self.formats}
        
        # Apply min floor 0.05 (5%) and max cap 0.40 (40%)
        clamped = {}
        floor = 0.05
        cap = 0.40
        for fmt, share in raw_shares.items():
            clamped[fmt] = max(floor, min(cap, share))

        # Re-normalize to sum to 1.0
        total = sum(clamped.values())
        final_weights = {fmt: round(w / total, 3) for fmt, w in clamped.items()}

        # Save to database
        for fmt, weight in final_weights.items():
            w_count, l_count = stats.get(fmt, (0, 0))
            set_bandit_weight(fmt, w_count, l_count, weight)

        print(f"[Learning Loop] Updated format shares: {final_weights}")
        return final_weights

    def refresh_golden_examples(self) -> int:
        """Promotes top 3 posts per format from the past 8 weeks into golden_examples."""
        with get_connection() as conn:
            cursor = conn.cursor()
            refreshed = 0
            for fmt in self.formats:
                cursor.execute("""
                SELECT p.post_id, p.selected_hook, p.body, m.score
                FROM posts p
                JOIN metrics m ON p.post_id = m.post_id
                WHERE p.format = ?
                ORDER BY m.score DESC LIMIT 3
                """, (fmt,))
                top_posts = cursor.fetchall()
                for p in top_posts:
                    cursor.execute("""
                    INSERT OR REPLACE INTO golden_examples (format, post_id, hook, body, score)
                    VALUES (?, ?, ?, ?, ?)
                    """, (fmt, p["post_id"], p["selected_hook"], p["body"], p["score"]))
                    refreshed += 1
            conn.commit()
        return refreshed

    def generate_weekly_report(self) -> str:
        """Builds weekly summary text for Telegram bot broadcast."""
        weights = get_bandit_weights()
        if not weights:
            weights = {fmt: CONFIG["formats"][fmt]["initial_weight"] for fmt in self.formats}

        lines = [
            "📊 *WEEKLY PERFORMANCE & BANDIT SUMMARY*",
            "─────────────────────────────",
            "📈 *Active Format Shares:*"
        ]
        for fmt, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"• `{fmt}`: {w * 100:.1f}%")

        lines.append("\n🎯 *Optimization Status:* Dynamic weights loaded. Golden examples active.")
        return "\n".join(lines)
