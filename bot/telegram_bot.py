"""
Telegram Approvals Bot.
Delivers daily candidate posts to your phone with interactive buttons:
[Approve] [Rewrite] [Reject]
Restricted exclusively to your Telegram User ID for total security.
Supports both Long Polling (local runner) and Webhook mode (Cloud Run/Workers).
"""

import os
import time
import json
import requests
from typing import Optional, Dict, Any, List
from utils.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID
from db.database import (
    get_pending_delivery_posts,
    update_post_status,
    get_connection,
    DEFAULT_DB_PATH
)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class TelegramApprovalBot:
    def __init__(self, token: Optional[str] = None, admin_chat_id: Optional[str] = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.admin_chat_id = str(admin_chat_id or TELEGRAM_ADMIN_CHAT_ID)
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}" if self.token else ""

    def is_configured(self) -> bool:
        return bool(self.token and self.admin_chat_id)

    def send_post_for_approval(self, post: Dict[str, Any]) -> bool:
        """Sends candidate card image and caption with inline approval buttons."""
        if not self.is_configured():
            print("[Bot] Telegram credentials not configured. Skipping delivery.")
            return False

        post_id = post["post_id"]
        card_image_path = post.get("card_image_path")
        full_caption = post.get("full_caption", "")
        
        # Inline keyboard
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{post_id}"},
                    {"text": "🔄 Rewrite", "callback_data": f"rewrite:{post_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{post_id}"}
                ]
            ]
        }

        try:
            # 1. Send card photo if available
            if card_image_path and os.path.exists(card_image_path):
                with open(card_image_path, "rb") as photo:
                    resp = requests.post(
                        f"{self.base_url}/sendPhoto",
                        data={"chat_id": self.admin_chat_id, "caption": f"📜 [{post['format'].upper()}] Proposal ({post['pillar']})"},
                        files={"photo": photo},
                        timeout=20
                    )
            
            # 2. Send text with buttons
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.admin_chat_id,
                    "text": f"*{post.get('selected_hook', '')}*\n\n{post.get('body', '')}\n\n_{post.get('source_line', '')}_\n\nPost ID: `{post_id}`",
                    "parse_mode": "Markdown",
                    "reply_markup": inline_keyboard
                },
                timeout=15
            )
            
            if resp.status_code == 200:
                print(f"[Bot] Successfully delivered candidate post {post_id} to Telegram.")
                return True
            else:
                print(f"[Bot] Delivery failed: {resp.text}")
                return False
        except Exception as e:
            print(f"[Bot] Telegram API exception: {e}")
            return False

    def deliver_all_pending(self) -> int:
        """Delivers all posts pending review."""
        posts = get_pending_delivery_posts()
        delivered = 0
        for p in posts:
            if self.send_post_for_approval(p):
                delivered += 1
                time.sleep(1.0)
        return delivered

    def handle_callback_query(self, query: Dict[str, Any]):
        """Processes button clicks from Telegram."""
        user_id = str(query.get("from", {}).get("id"))
        if user_id != self.admin_chat_id:
            print(f"[Bot] Unauthorized callback from user: {user_id}")
            return

        query_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        message_id = message.get("message_id")
        
        parts = data.split(":")
        if len(parts) != 2:
            return
            
        action, post_id = parts[0], parts[1]
        
        if action == "approve":
            update_post_status(post_id, "approved")
            notification = f"✅ Post {post_id} Approved! Queued for Meta scheduler."
        elif action == "reject":
            update_post_status(post_id, "rejected")
            notification = f"❌ Post {post_id} Rejected."
        elif action == "rewrite":
            notification = f"🔄 Reply to this message with rewrite instructions for {post_id}."
        else:
            notification = "Action not recognized."

        # Acknowledge callback
        requests.post(f"{self.base_url}/answerCallbackQuery", json={"callback_query_id": query_id, "text": notification})
        # Edit message to reflect decision
        requests.post(
            f"{self.base_url}/editMessageText",
            json={
                "chat_id": self.admin_chat_id,
                "message_id": message_id,
                "text": f"{message.get('text', '')}\n\n**STATUS: {notification}**",
                "parse_mode": "Markdown"
            }
        )

    def handle_message(self, message: Dict[str, Any]):
        """Handles manual edit commands or rewrite notes from the admin."""
        user_id = str(message.get("from", {}).get("id"))
        if user_id != self.admin_chat_id:
            return

        text = message.get("text", "")
        
        # Check for quick edit: "edit: <post_id> <new body>"
        if text.startswith("edit:"):
            parts = text[5:].strip().split(" ", 1)
            if len(parts) == 2:
                post_id, new_body = parts[0], parts[1]
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE posts SET body = ?, status = 'approved' WHERE post_id = ?", (new_body, post_id))
                    conn.commit()
                requests.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.admin_chat_id, "text": f"✏️ Post {post_id} updated and approved!"}
                )

    def run_polling(self):
        """Runs interactive long-polling loop for local development/testing."""
        if not self.is_configured():
            print("[Bot] Telegram credentials missing. Set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID in .env.")
            return

        print(f"[Bot] Starting Telegram bot polling for admin: {self.admin_chat_id}...")
        offset = 0
        while True:
            try:
                resp = requests.get(f"{self.base_url}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25)
                if resp.status_code == 200:
                    updates = resp.json().get("result", [])
                    for u in updates:
                        offset = u["update_id"] + 1
                        if "callback_query" in u:
                            self.handle_callback_query(u["callback_query"])
                        elif "message" in u:
                            self.handle_message(u["message"])
                time.sleep(1.0)
            except KeyboardInterrupt:
                print("\n[Bot] Stopped by user.")
                break
            except Exception as e:
                print(f"[Bot] Polling error: {e}")
                time.sleep(5.0)
