# Archive Micro-Story Facebook Automation Engine

An autonomous, self-improving content engine for the Facebook Page **"Old news, modern life"**.
Built strictly around authentic public-domain archive clippings (pre-1930 Chronicling America / Library of Congress), verified with code gates and citation matching, curated via a judge tournament, and approved directly from your phone via Telegram.

---

## Architecture Overview

```
Archive Records (LoC / Curated) 
       │
       ▼
1. HARVEST (Seed Cards, Keywords, Price/Ad/Advice/Incident)
       │
       ▼
2. DRAFT (Gemini generates 3 candidates x 5 hooks, structured claims)
       │
       ▼
3. GATES (Word count, Banned AI words, Exclamation limits, Cosine similarity, Citation match >= 90%)
       │
       ▼
4. JUDGE TOURNAMENT (Gemini Judge scores 1-10; Winner polished with Section 5 rules)
       │
       ▼
5. RENDER (1080x1350 High-res Portrait Cards via Pillow + Typography + CPI Badges)
       │
       ▼
6. TELEGRAM APPROVAL (Delivered to phone: [Approve] [Rewrite] [Reject])
       │
       ▼
7. META SCHEDULER (Scheduled via Graph API in peak US/UK engagement windows)
       │
       ▼
8. LEARNING LOOP (Thompson Sampling on Beta(wins, losses); Format shares dynamically reweighted)
```

---

## Quick Start Guide

### 1. Configure Environment
Create a `.env` file in the project root (see `.env.example`):
```env
# 1. Gemini API Key
GEMINI_API_KEY=your_key_here

# 2. Meta Facebook Graph API
META_PAGE_ID=your_page_id_here
META_PAGE_ACCESS_TOKEN=your_never_expiring_system_user_page_token

# 3. Telegram Approval Bot
TELEGRAM_BOT_TOKEN=your_botfather_token
TELEGRAM_ADMIN_CHAT_ID=your_numeric_telegram_user_id
```

### 2. Check System Health
```bash
python main.py health
```

### 3. Generate Posts & Cards
```bash
# Generate 1 post for each of the 6 formats:
python main.py generate

# Or generate for a specific format:
python main.py generate --format price
python main.py generate --format true_retelling
python main.py generate --format advice
```

### 4. Deliver to Telegram for Phone Approval
```bash
python main.py deliver
```
Or start the interactive Telegram bot listener:
```bash
python main.py bot
```

### 5. Schedule Approved Posts on Facebook
```bash
python main.py schedule
```

### 6. Sync Insights & Run Learning Loop (Sundays)
```bash
python main.py metrics
python main.py learn
```
