"""
System Health and Diagnostics Monitor.
Checks:
- API Keys and token statuses
- Seed card inventory levels per format (alerts when < 10)
- Pending approval queue length
- Scheduled post buffer
"""

import os
from typing import Dict, Any
from utils.config import (
    GEMINI_API_KEY,
    META_PAGE_ID,
    META_PAGE_ACCESS_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ADMIN_CHAT_ID,
    CONFIG
)
from db.database import get_seed_stock_counts, get_connection

class HealthMonitor:
    def check_health(self) -> Dict[str, Any]:
        report = {
            "gemini_api_configured": bool(GEMINI_API_KEY),
            "meta_api_configured": bool(META_PAGE_ID and META_PAGE_ACCESS_TOKEN),
            "telegram_bot_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID),
            "seed_stock": get_seed_stock_counts(),
            "stock_alerts": [],
            "queue_counts": {}
        }
        
        # Check stock against alert threshold
        threshold = CONFIG.get("harvest", {}).get("stock_alert_threshold", 10)
        for fmt in CONFIG["formats"]:
            current = report["seed_stock"].get(fmt, 0)
            if current < threshold:
                report["stock_alerts"].append(f"Format '{fmt}' is low on stock ({current} / {threshold})")

        # Check queues
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as cnt FROM posts GROUP BY status")
            rows = cursor.fetchall()
            report["queue_counts"] = {r["status"]: r["cnt"] for r in rows}

        return report

    def print_diagnostics(self):
        h = self.check_health()
        print("=" * 50)
        print("🔍 ARCHIVE MICRO-STORY SYSTEM HEALTH REPORT")
        print("=" * 50)
        print(f"• Gemini API Key:     {'✅ Configured' if h['gemini_api_configured'] else '❌ Missing in .env'}")
        print(f"• Meta Graph API:     {'✅ Configured' if h['meta_api_configured'] else '❌ Missing in .env'}")
        print(f"• Telegram Bot:       {'✅ Configured' if h['telegram_bot_configured'] else '❌ Missing in .env'}")
        print("\n📦 Seed Stock by Format:")
        for fmt, cnt in h["seed_stock"].items():
            print(f"  - {fmt:15}: {cnt} available")
        if not h["seed_stock"]:
            print("  - No seeds in stock.")
            
        if h["stock_alerts"]:
            print("\n⚠️ Stock Alerts:")
            for a in h["stock_alerts"]:
                print(f"  - {a}")
                
        print("\n📋 Post Queue Status:")
        for st, count in h["queue_counts"].items():
            print(f"  - {st:18}: {count}")
        if not h["queue_counts"]:
            print("  - Queue empty.")
        print("=" * 50)
