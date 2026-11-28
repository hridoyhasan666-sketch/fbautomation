"""
Telegram Approvals Bot.
Sends each new post (card + exact Facebook caption) to your phone with [Approve] [Reject] buttons.
Only your TELEGRAM_ADMIN_CHAT_ID can press them.

- `deliver`: sends posts not yet delivered (each post is sent once).
- `poll`:    processes button presses once and exits (used by GitHub Actions).
- `bot`:     long-polling loop for running on your own machine.
"""

import html
import time
import requests
from typing import Optional, Dict, Any
from utils.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID
from db.database import get_pending_delivery_posts, update_post_status, get_post_status, set_telegram_message_id
from render.card import resolve_path

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramApprovalBot:
    def __init__(self, token: Optional[str] = None, admin_chat_id: Optional[str] = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.admin_chat_id = str(admin_chat_id or TELEGRAM_ADMIN_CHAT_ID)
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}" if self.token else ""

    def is_configured(self) -> bool:
        return bool(self.token and self.admin_chat_id)

    def _api(self, method: str, **kwargs) -> Dict[str, Any]:
        try:
            return requests.post(f"{self.base_url}/{method}", timeout=30, **kwargs).json()
        except Exception as e:
            print(f"[Bot] Telegram {method} error: {e}")
            return {"ok": False}

    def send_post_for_approval(self, post: Dict[str, Any]) -> bool:
        post_id = post["post_id"]
        card = resolve_path(post.get("card_image_path") or "")
        try:
            with open(card, "rb") as photo:
                self._api("sendPhoto",
                          data={"chat_id": self.admin_chat_id,
                                "caption": f"[{post['format']}] {post.get('topic') or ''}"[:1000]},
                          files={"photo": photo})
        except OSError:
            pass

        text = (f"{html.escape(post.get('full_caption', ''))}\n\n"
                f"<i>{html.escape(post['format'])} · {html.escape(post.get('pillar', ''))}</i>\n"
                f"<i>Tap once. Your choice is applied within ~10 minutes and this message will show STATUS.</i>\n"
                f"<code>{post_id}</code>")
        res = self._api("sendMessage", json={
            "chat_id": self.admin_chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve:{post_id}"},
                {"text": "❌ Reject", "callback_data": f"reject:{post_id}"},
            ]]},
        })
        if res.get("ok"):
            set_telegram_message_id(post_id, res["result"]["message_id"])
            print(f"[Bot] Delivered {post_id}.")
            return True
        print(f"[Bot] Delivery failed for {post_id}: {res}")
        return False

    def deliver_all_pending(self) -> int:
        if not self.is_configured():
            print("[Bot] Telegram not configured.")
            return 0
        delivered = 0
        for p in get_pending_delivery_posts():
            if self.send_post_for_approval(p):
                delivered += 1
                time.sleep(1.0)
        return delivered

    def handle_callback_query(self, query: Dict[str, Any]):
        if str(query.get("from", {}).get("id")) != self.admin_chat_id:
            print("[Bot] Ignored callback from unauthorised user.")
            return

        action, _, post_id = query.get("data", "").partition(":")
        current = get_post_status(post_id)
        if current is None:
            note = "Post not found."
        elif current != "pending_approval":
            note = f"Already {current}."
        elif action == "approve":
            update_post_status(post_id, "approved")
            note = "Approved - it will be scheduled at the next free random slot."
        elif action in ("reject", "rewrite"):
            update_post_status(post_id, "rejected")
            note = "Rejected."
        else:
            note = "Unknown action."

        self._api("answerCallbackQuery", json={"callback_query_id": query.get("id"), "text": note[:190]})
        msg = query.get("message", {})
        if msg.get("message_id"):
            self._api("editMessageText", json={
                "chat_id": self.admin_chat_id,
                "message_id": msg["message_id"],
                "text": f"{msg.get('text', '')}\n\nSTATUS: {note}"[:4096],
            })
        print(f"[Bot] {post_id}: {note}")

    def process_updates_once(self, offset: int = 0, wait: int = 0) -> int:
        """Handles all queued button presses. Returns the next offset."""
        try:
            resp = requests.get(f"{self.base_url}/getUpdates",
                                params={"offset": offset, "timeout": wait,
                                        "allowed_updates": '["callback_query"]'},
                                timeout=wait + 15).json()
        except Exception as e:
            print(f"[Bot] getUpdates error: {e}")
            return offset
        if not resp.get("ok"):
            print(f"[Bot] getUpdates failed: {resp.get('error_code')} {resp.get('description')}")
            return offset
        if resp.get("result"):
            print(f"[Bot] Received {len(resp['result'])} update(s).")
        for u in resp.get("result", []):
            offset = u["update_id"] + 1
            if "callback_query" in u:
                self.handle_callback_query(u["callback_query"])
        return offset

    def poll_once(self) -> None:
        if not self.is_configured():
            print("[Bot] Telegram not configured.")
            return
        me = self._api("getMe").get("result", {})
        hook = self._api("getWebhookInfo").get("result", {})
        print(f"[Bot] Polling as @{me.get('username')}; webhook={'set' if hook.get('url') else 'none'}; "
              f"pending={hook.get('pending_update_count')}")
        if hook.get("url"):
            # A webhook blocks getUpdates entirely; drop it so button presses reach us.
            print(f"[Bot] Removing webhook so polling works: {self._api('deleteWebhook')}")
        offset = self.process_updates_once()
        # Confirm processed updates so Telegram doesn't resend them next time.
        if offset:
            self.process_updates_once(offset)

    def run_polling(self):
        if not self.is_configured():
            print("[Bot] Telegram not configured.")
            return
        print(f"[Bot] Polling for button presses (admin {self.admin_chat_id})...")
        offset = 0
        while True:
            try:
                offset = self.process_updates_once(offset, wait=20)
            except KeyboardInterrupt:
                print("\n[Bot] Stopped.")
                break
