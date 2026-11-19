"""
Meta Facebook Graph API Publisher and Scheduler.
Schedules approved posts to Meta via POST /{page-id}/photos or POST /{page-id}/feed
with published=false and scheduled_publish_time in peak US/UK engagement windows.
"""

import os
import random
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from utils.config import CONFIG, META_PAGE_ID, META_PAGE_ACCESS_TOKEN
from db.database import get_approved_unscheduled_posts, update_post_status

GRAPH_API_VERSION = CONFIG.get("meta", {}).get("graph_api_version", "v21.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

class MetaPublisher:
    def __init__(self, page_id: Optional[str] = None, access_token: Optional[str] = None):
        self.page_id = page_id or META_PAGE_ID
        self.access_token = access_token or META_PAGE_ACCESS_TOKEN

    def is_configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    def test_visibility_post(self, message: str = "Archive discovery test post. Real history, modern mirrors.") -> Dict[str, Any]:
        """
        Phase 2 Verification Test:
        Publishes one immediate public text post to prove Business App & Page token permissions work.
        """
        if not self.is_configured():
            return {"success": False, "error": "META_PAGE_ID or META_PAGE_ACCESS_TOKEN is missing in .env"}

        url = f"{GRAPH_BASE_URL}/{self.page_id}/feed"
        payload = {
            "message": message,
            "access_token": self.access_token
        }
        
        try:
            resp = requests.post(url, data=payload, timeout=20)
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                print(f"[Meta] Visibility test succeeded! Post ID: {data['id']}")
                return {"success": True, "post_id": data["id"]}
            else:
                print(f"[Meta] Visibility test failed: {data}")
                return {"success": False, "error": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calculate_next_slot(self, existing_schedules: List[datetime]) -> int:
        """
        Calculates a scheduled unix timestamp in peak US/UK windows (12:00-23:00 UTC).
        Must be at least 15 minutes in the future and at least 2.5 hours after previous post.
        """
        now = datetime.now(timezone.utc)
        windows = CONFIG.get("meta", {}).get("daily_posting_windows_utc", [
            {"start": 12, "end": 14},
            {"start": 16, "end": 18},
            {"start": 20, "end": 22}
        ])
        
        # Start looking from tomorrow or later today
        candidate_days = [now.date() + timedelta(days=d) for d in range(1, 8)]
        
        for day in candidate_days:
            for w in windows:
                rand_minute = random.randint(5, 50)
                rand_second = random.randint(0, 59)
                slot_time = datetime(
                    day.year, day.month, day.day,
                    w["start"], rand_minute, rand_second,
                    tzinfo=timezone.utc
                )
                
                # Check conflict with existing schedules
                conflict = False
                for ex in existing_schedules:
                    diff_hours = abs((slot_time - ex).total_seconds()) / 3600.0
                    if diff_hours < 2.5:
                        conflict = True
                        break
                        
                if not conflict:
                    existing_schedules.append(slot_time)
                    return int(slot_time.timestamp())
                    
        # Fallback to tomorrow + 24 hours
        fallback = now + timedelta(days=1, hours=random.randint(12, 20))
        return int(fallback.timestamp())

    def schedule_post(self, post: Dict[str, Any], scheduled_timestamp: int) -> Optional[str]:
        """
        Schedules a single approved post on Meta Facebook Graph API.
        """
        if not self.is_configured():
            print("[Meta] Missing credentials. Simulating post schedule in dry-run mode.")
            simulated_id = f"simulated_fb_{post['post_id']}"
            update_post_status(post["post_id"], "scheduled", fb_post_id=simulated_id)
            return simulated_id

        caption = post.get("full_caption", "")
        card_image_path = post.get("card_image_path")
        
        try:
            if card_image_path and os.path.exists(card_image_path):
                # Photo post schedule
                url = f"{GRAPH_BASE_URL}/{self.page_id}/photos"
                with open(card_image_path, "rb") as f:
                    payload = {
                        "caption": caption,
                        "published": "false",
                        "scheduled_publish_time": scheduled_timestamp,
                        "access_token": self.access_token
                    }
                    resp = requests.post(url, data=payload, files={"source": f}, timeout=30)
            else:
                # Feed post schedule
                url = f"{GRAPH_BASE_URL}/{self.page_id}/feed"
                payload = {
                    "message": caption,
                    "published": "false",
                    "scheduled_publish_time": scheduled_timestamp,
                    "access_token": self.access_token
                }
                resp = requests.post(url, data=payload, timeout=20)

            data = resp.json()
            if resp.status_code == 200 and ("id" in data or "post_id" in data):
                fb_id = data.get("post_id") or data.get("id")
                print(f"[Meta] Post {post['post_id']} successfully scheduled! FB ID: {fb_id}")
                update_post_status(post["post_id"], "scheduled", fb_post_id=fb_id)
                return fb_id
            else:
                print(f"[Meta] Scheduling error from Facebook: {data}")
                return None
        except Exception as e:
            print(f"[Meta] Network error scheduling post: {e}")
            return None

    def run_scheduling_job(self) -> int:
        """Processes all approved, unscheduled posts."""
        posts = get_approved_unscheduled_posts()
        if not posts:
            print("[Scheduler] No approved posts waiting to be scheduled.")
            return 0

        scheduled_count = 0
        existing_slots = []
        last_format = ""

        for p in posts:
            # Avoid two of same format back to back
            if p["format"] == last_format and len(posts) > 1:
                continue
                
            slot_ts = self.calculate_next_slot(existing_slots)
            fb_id = self.schedule_post(p, slot_ts)
            if fb_id:
                scheduled_count += 1
                last_format = p["format"]

        return scheduled_count
