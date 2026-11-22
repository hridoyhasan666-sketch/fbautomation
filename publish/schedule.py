"""
Meta Facebook Graph API Publisher and Scheduler.

Schedules approved posts with published=false + scheduled_publish_time.
Rules:
- At most `posts_per_day` posts per UTC day, at most one per posting window.
- Each post gets a random minute inside its window, and at least `min_gap_hours` from any other post.
- Already-taken slots come from BOTH the local DB and Facebook's own scheduled-post list,
  so repeated runs (every 2h on GitHub Actions) never stack posts on the same time.
"""

import random
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from utils.config import CONFIG, META_PAGE_ID, META_PAGE_ACCESS_TOKEN
from db.database import get_approved_unscheduled_posts, update_post_status, get_scheduled_publish_times
from render.card import resolve_path

META_CFG = CONFIG.get("meta", {})
GRAPH_BASE_URL = f"https://graph.facebook.com/{META_CFG.get('graph_api_version', 'v21.0')}"
DEFAULT_WINDOWS = [{"start": 12, "end": 15}, {"start": 16, "end": 19}, {"start": 20, "end": 23}]


def pick_slot(taken: List[int], now: Optional[datetime] = None) -> Optional[int]:
    """Returns a unix timestamp for the next free random slot, or None if the lookahead is full."""
    now = now or datetime.now(timezone.utc)
    windows = META_CFG.get("daily_posting_windows_utc", DEFAULT_WINDOWS)
    per_day = META_CFG.get("posts_per_day", 3)
    gap = META_CFG.get("min_gap_hours", 2.5) * 3600
    days_ahead = META_CFG.get("schedule_days_ahead", 3)
    earliest = now + timedelta(minutes=20)  # Facebook requires >= 10 minutes ahead

    taken_dt = [datetime.fromtimestamp(t, tz=timezone.utc) for t in taken]

    for offset in range(days_ahead + 1):
        day = (now + timedelta(days=offset)).date()
        on_day = [t for t in taken_dt if t.date() == day]
        if len(on_day) >= per_day:
            continue

        for w in windows:
            w_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=w["start"])
            w_end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=w["end"])
            if any(w_start <= t < w_end for t in on_day):
                continue  # one post per window
            lo = max(w_start, earliest)
            if lo >= w_end:
                continue
            span = int((w_end - lo).total_seconds()) - 60
            if span <= 0:
                continue
            for _ in range(30):
                cand = lo + timedelta(seconds=random.randint(0, span))
                if all(abs((cand - t).total_seconds()) >= gap for t in taken_dt):
                    return int(cand.timestamp())
    return None


class MetaPublisher:
    def __init__(self, page_id: Optional[str] = None, access_token: Optional[str] = None):
        self.page_id = page_id or META_PAGE_ID
        self.access_token = access_token or META_PAGE_ACCESS_TOKEN

    def is_configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    def fetch_facebook_scheduled_times(self) -> List[int]:
        """Scheduled posts that Facebook already holds for the page."""
        if not self.is_configured():
            return []
        out, url = [], f"{GRAPH_BASE_URL}/{self.page_id}/scheduled_posts"
        params = {"fields": "scheduled_publish_time", "limit": 100, "access_token": self.access_token}
        try:
            while url:
                data = requests.get(url, params=params, timeout=20).json()
                if "error" in data:
                    print(f"[Meta] Could not read scheduled posts: {data['error'].get('message')}")
                    break
                out += [int(p["scheduled_publish_time"]) for p in data.get("data", []) if p.get("scheduled_publish_time")]
                url, params = data.get("paging", {}).get("next"), None
        except Exception as e:
            print(f"[Meta] Error reading scheduled posts: {e}")
        return out

    def test_visibility_post(self, message: str = "Test post from Sincerely Yours.") -> Dict[str, Any]:
        """Publishes one immediate public text post to check token permissions."""
        if not self.is_configured():
            return {"success": False, "error": "META_PAGE_ID or META_PAGE_ACCESS_TOKEN missing"}
        resp = requests.post(f"{GRAPH_BASE_URL}/{self.page_id}/feed",
                             data={"message": message, "access_token": self.access_token}, timeout=20)
        data = resp.json()
        print(f"[Meta] Test post result: {data}")
        return {"success": "id" in data, "result": data}

    def schedule_post(self, post: Dict[str, Any], ts: int) -> Optional[str]:
        if not self.is_configured():
            print("[Meta] Missing credentials; not scheduling.")
            return None

        caption = post.get("full_caption", "")
        card = resolve_path(post.get("card_image_path") or "")
        common = {"published": "false", "scheduled_publish_time": ts, "access_token": self.access_token}
        try:
            try:
                f = open(card, "rb") if card else None
            except OSError:
                f = None
            if f:
                with f:
                    resp = requests.post(f"{GRAPH_BASE_URL}/{self.page_id}/photos",
                                         data={**common, "caption": caption}, files={"source": f}, timeout=60)
            else:
                print(f"[Meta] Card image not found for {post['post_id']}; posting text only.")
                resp = requests.post(f"{GRAPH_BASE_URL}/{self.page_id}/feed",
                                     data={**common, "message": caption}, timeout=30)
            data = resp.json()
        except Exception as e:
            print(f"[Meta] Network error scheduling {post['post_id']}: {e}")
            return None

        fb_id = data.get("post_id") or data.get("id")
        if resp.status_code == 200 and fb_id:
            when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            print(f"[Meta] Scheduled {post['post_id']} for {when} (FB ID {fb_id})")
            update_post_status(post["post_id"], "scheduled", fb_post_id=fb_id, scheduled_publish_time=ts)
            return fb_id
        print(f"[Meta] Facebook rejected {post['post_id']}: {data}")
        return None

    def run_scheduling_job(self) -> int:
        posts = get_approved_unscheduled_posts()
        if not posts:
            print("[Scheduler] No approved posts waiting.")
            return 0

        now_ts = int(datetime.now(timezone.utc).timestamp())
        taken = sorted(set(get_scheduled_publish_times() + self.fetch_facebook_scheduled_times()))
        print(f"[Scheduler] {len([t for t in taken if t > now_ts])} posts already queued on Facebook.")

        count = 0
        for p in posts:
            ts = pick_slot(taken)
            if ts is None:
                print("[Scheduler] Posting calendar is full for the lookahead window; remaining posts wait for the next run.")
                break
            if self.schedule_post(p, ts):
                taken.append(ts)
                count += 1
        return count
