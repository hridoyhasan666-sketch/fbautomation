"""
Configuration and Environment Loader.
"""

import os
import yaml
from typing import Any, Dict
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()

# Helper accessors
def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)

GEMINI_API_KEY = get_env("GEMINI_API_KEY")
META_PAGE_ID = get_env("META_PAGE_ID")
META_PAGE_ACCESS_TOKEN = get_env("META_PAGE_ACCESS_TOKEN")
META_APP_ID = get_env("META_APP_ID")
META_APP_SECRET = get_env("META_APP_SECRET")
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = get_env("TELEGRAM_ADMIN_CHAT_ID")
ASSETS_BASE_URL = get_env("ASSETS_BASE_URL")
