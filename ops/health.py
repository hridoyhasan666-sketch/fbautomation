"""
System Health Monitor: credentials, post queue, and upcoming Facebook schedule.
"""

from datetime import datetime, timezone
from utils.config import GEMINI_API_KEY, META_PAGE_ID, META_PAGE_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID
from db.database import get_connection, get_scheduled_publish_times


class HealthMonitor:
    def print_diagnostics(self):
        ok = lambda b: "OK" if b else "MISSING"
        print("=" * 50)
        print("SINCERELY YOURS - SYSTEM HEALTH")
        print("=" * 50)
        print(f"Gemini API:   {ok(GEMINI_API_KEY)}")
        print(f"Meta Graph:   {ok(META_PAGE_ID and META_PAGE_ACCESS_TOKEN)}")
        print(f"Telegram bot: {ok(TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID)}")

        with get_connection() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM posts GROUP BY status").fetchall()
        print("\nPost queue:")
        for r in rows:
            print(f"  {r['status']:18} {r['cnt']}")

        now = datetime.now(timezone.utc).timestamp()
        upcoming = sorted(t for t in get_scheduled_publish_times() if t > now)
        print("\nUpcoming Facebook posts (UTC):")
        for t in upcoming:
            print("  " + datetime.fromtimestamp(t, tz=timezone.utc).strftime("%a %Y-%m-%d %H:%M"))
        if not upcoming:
            print("  none")
        print("=" * 50)
