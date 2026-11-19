"""
Post Insights & Metrics Harvester.
Queries Meta Facebook Graph API for 48-hour engagement:
Reach, reactions, comments, shares, and updates the local metrics table.
"""

import requests
from typing import Dict, Any, List
from utils.config import CONFIG, META_PAGE_ACCESS_TOKEN
from db.database import get_connection
from learn.bandit import LearningLoop

GRAPH_API_VERSION = CONFIG.get("meta", {}).get("graph_api_version", "v21.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

class MetricsHarvester:
    def __init__(self, access_token: str = META_PAGE_ACCESS_TOKEN):
        self.access_token = access_token
        self.loop = LearningLoop()

    def fetch_post_metrics(self, fb_post_id: str) -> Dict[str, int]:
        """Fetches post metrics from Graph API."""
        if not self.access_token or fb_post_id.startswith("simulated"):
            # Mock / simulated engagement for dry run or offline testing
            return {"reach": 1250, "reactions": 42, "comments": 8, "shares": 6}

        url = f"{GRAPH_BASE_URL}/{fb_post_id}"
        params = {
            "fields": "shares,reactions.summary(total_count),comments.summary(total_count),insights.metric(post_impressions_unique)",
            "access_token": self.access_token
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                shares = data.get("shares", {}).get("count", 0)
                reactions = data.get("reactions", {}).get("summary", {}).get("total_count", 0)
                comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
                
                reach = 500 # Default baseline
                insights = data.get("insights", {}).get("data", [])
                for i in insights:
                    if i.get("name") == "post_impressions_unique":
                        reach = i.get("values", [{}])[0].get("value", 500)

                return {"reach": reach, "reactions": reactions, "comments": comments, "shares": shares}
        except Exception as e:
            print(f"[Metrics] Error pulling metrics for {fb_post_id}: {e}")

        return {"reach": 0, "reactions": 0, "comments": 0, "shares": 0}

    def sync_all_published_posts(self) -> int:
        """Updates metrics for all scheduled or published posts."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT post_id, fb_post_id FROM posts WHERE fb_post_id IS NOT NULL")
            posts = cursor.fetchall()

        synced = 0
        for p in posts:
            m = self.fetch_post_metrics(p["fb_post_id"])
            score = self.loop.calculate_post_score(m["reactions"], m["comments"], m["shares"], m["reach"])
            
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT OR REPLACE INTO metrics (post_id, reach, reactions, comments, shares, score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (p["post_id"], m["reach"], m["reactions"], m["comments"], m["shares"], score))
                conn.commit()
            synced += 1

        print(f"[Metrics] Synced engagement metrics for {synced} posts.")
        return synced
