"""
SQLite Database Layer for Archive Micro-Story System.
Tracks seeds, candidate drafts, approvals, scheduled posts, metrics, bandit weights, and hook history.
"""

import sqlite3
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "archive_stories.db")

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH):
    """Initializes all necessary tables."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Seeds table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS seeds (
            seed_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_url TEXT,
            page_image_url TEXT,
            date TEXT,
            place TEXT,
            ocr_text TEXT,
            format TEXT NOT NULL,
            pillar TEXT NOT NULL,
            facts_json TEXT,
            human_need TEXT,
            modern_mirror TEXT,
            price_data_json TEXT,
            ad_crop_clues TEXT,
            safety_flags_json TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 2. Candidates & Drafts
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            seed_id TEXT NOT NULL,
            format TEXT NOT NULL,
            persona TEXT NOT NULL,
            hooks_json TEXT,
            body TEXT NOT NULL,
            claims_json TEXT,
            source_line TEXT,
            card_text TEXT,
            judge_scores_json TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
        )
        """)
        
        # 3. Posts & Pipeline Queue
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            seed_id TEXT NOT NULL,
            candidate_id TEXT,
            format TEXT NOT NULL,
            pillar TEXT NOT NULL,
            selected_hook TEXT NOT NULL,
            body TEXT NOT NULL,
            source_line TEXT,
            full_caption TEXT NOT NULL,
            card_image_path TEXT,
            reel_video_path TEXT,
            status TEXT DEFAULT 'pending_approval',
            telegram_message_id INTEGER,
            scheduled_publish_time TIMESTAMP,
            fb_post_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP,
            FOREIGN KEY (seed_id) REFERENCES seeds (seed_id)
        )
        """)
        
        # 4. Metrics & Performance
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            post_id TEXT PRIMARY KEY,
            reach INTEGER DEFAULT 0,
            reactions INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            score REAL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts (post_id)
        )
        """)
        
        # 5. Bandit Weights for Learning Loop
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bandit_weights (
            format TEXT PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            current_weight REAL DEFAULT 0.15,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 6. Golden Examples
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS golden_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            format TEXT NOT NULL,
            post_id TEXT NOT NULL,
            hook TEXT NOT NULL,
            body TEXT NOT NULL,
            score REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 7. Hook History (for repeat gate)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hook_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hook_text TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        conn.commit()

# --- Seed Operations ---

def save_seed(seed_data: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
            INSERT OR REPLACE INTO seeds (
                seed_id, source, source_url, page_image_url, date, place, ocr_text,
                format, pillar, facts_json, human_need, modern_mirror, price_data_json,
                ad_crop_clues, safety_flags_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                seed_data["seed_id"],
                seed_data.get("source", "Chronicling America"),
                seed_data.get("source_url", ""),
                seed_data.get("page_image_url", ""),
                seed_data.get("date", ""),
                seed_data.get("place", ""),
                seed_data.get("ocr_text", ""),
                seed_data["format"],
                seed_data["pillar"],
                json.dumps(seed_data.get("facts", [])),
                seed_data.get("human_need", ""),
                seed_data.get("modern_mirror", ""),
                json.dumps(seed_data.get("price_data", {})),
                seed_data.get("ad_crop_clues", ""),
                json.dumps(seed_data.get("safety_flags", [])),
                seed_data.get("status", "new")
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving seed: {e}")
            return False

def get_seed_stock_counts(db_path: str = DEFAULT_DB_PATH) -> Dict[str, int]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT format, COUNT(*) as cnt FROM seeds WHERE status = 'new' GROUP BY format")
        rows = cursor.fetchall()
        return {row["format"]: row["cnt"] for row in rows}

def get_next_seed_for_format(format_name: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM seeds 
        WHERE format = ? AND status = 'new' 
        ORDER BY created_at ASC LIMIT 1
        """, (format_name,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["facts"] = json.loads(res["facts_json"]) if res["facts_json"] else []
        res["price_data"] = json.loads(res["price_data_json"]) if res["price_data_json"] else {}
        res["safety_flags"] = json.loads(res["safety_flags_json"]) if res["safety_flags_json"] else []
        return res

def mark_seed_used(seed_id: str, db_path: str = DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE seeds SET status = 'used' WHERE seed_id = ?", (seed_id,))
        conn.commit()

# --- Post Operations ---

def save_post(post_data: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO posts (
            post_id, seed_id, candidate_id, format, pillar, selected_hook,
            body, source_line, full_caption, card_image_path, reel_video_path,
            status, telegram_message_id, scheduled_publish_time, fb_post_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_data["post_id"],
            post_data["seed_id"],
            post_data.get("candidate_id"),
            post_data["format"],
            post_data["pillar"],
            post_data["selected_hook"],
            post_data["body"],
            post_data.get("source_line", ""),
            post_data["full_caption"],
            post_data.get("card_image_path", ""),
            post_data.get("reel_video_path", ""),
            post_data.get("status", "pending_approval"),
            post_data.get("telegram_message_id"),
            post_data.get("scheduled_publish_time"),
            post_data.get("fb_post_id")
        ))
        conn.commit()

def update_post_status(post_id: str, status: str, fb_post_id: Optional[str] = None, db_path: str = DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if fb_post_id:
            cursor.execute("UPDATE posts SET status = ?, fb_post_id = ? WHERE post_id = ?", (status, fb_post_id, post_id))
        else:
            cursor.execute("UPDATE posts SET status = ? WHERE post_id = ?", (status, post_id))
        conn.commit()

def get_pending_delivery_posts(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE status = 'pending_approval' ORDER BY created_at ASC")
        return [dict(r) for r in cursor.fetchall()]

def get_approved_unscheduled_posts(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE status = 'approved' AND (fb_post_id IS NULL OR fb_post_id = '') ORDER BY created_at ASC")
        return [dict(r) for r in cursor.fetchall()]

# --- Hook History & Similarity ---

def get_recent_hooks(limit: int = 60, db_path: str = DEFAULT_DB_PATH) -> List[str]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT hook_text FROM hook_history ORDER BY id DESC LIMIT ?", (limit,))
        return [r["hook_text"] for r in cursor.fetchall()]

def add_hook_to_history(hook: str, db_path: str = DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR IGNORE INTO hook_history (hook_text) VALUES (?)", (hook,))
            conn.commit()
        except Exception:
            pass

# --- Bandit Weights & Golden Examples ---

def get_bandit_weights(db_path: str = DEFAULT_DB_PATH) -> Dict[str, float]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT format, current_weight FROM bandit_weights")
        rows = cursor.fetchall()
        return {r["format"]: r["current_weight"] for r in rows}

def set_bandit_weight(format_name: str, wins: int, losses: int, weight: float, db_path: str = DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO bandit_weights (format, wins, losses, current_weight, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (format_name, wins, losses, weight))
        conn.commit()

def get_golden_examples(format_name: str, limit: int = 3, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM golden_examples 
        WHERE format = ? 
        ORDER BY score DESC LIMIT ?
        """, (format_name, limit))
        return [dict(r) for r in cursor.fetchall()]
