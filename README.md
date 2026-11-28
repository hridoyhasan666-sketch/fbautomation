# Sincerely Yours — Facebook Content Engine

Automated posting for the Facebook Page **Sincerely Yours** ("Old news, modern life"):
original posts comparing how people lived ~100 years ago with how we live now.

## Daily flow (GitHub Actions)

| When (UTC) | Workflow | What it does |
|---|---|---|
| 02:00 daily | `generate.yml` | Writes 3 posts (3 drafts each → quality gates → AI judge → polish → card image), sends each to Telegram |
| on tap (instant) | `approve.yml` | Cloudflare Worker (`worker/`) answers the button, then this saves the decision and schedules on Facebook (~1 min) |
| ~hourly | `schedule.yml` | Backup: schedules any approved post still waiting (and reads taps if the worker is off) |
| Sun 18:00 | `learn.yml` | Pulls engagement, shifts format mix toward what performs |

Scheduling rules (`config.yaml → meta`): max **3 posts/day**, one per window
(12–15, 16–19, 20–23 UTC), random minute, at least 2.5h apart. Slots already taken are read from
both the database and Facebook's own scheduled-post list, so posts never stack.

## Current content: guess-the-quote photocards
Each post is a card with a public-domain quote (no author shown) and a short caption:
"Can you guess the writer?" or "Which book is this from?" plus hashtags. The answer appears only in
your Telegram approval message. Quotes live in `data/quotes.yaml` (add your own there); each is used
once before any repeats. Hashtags: `config.yaml -> quotes`. To bring back the older written formats,
edit `generation.enabled_formats` in `config.yaml`.

## Older formats (`formats/`)
`then_vs_now`, `forgotten_habit`, `old_wisdom`, `life_question`, `short_story` (labelled fiction).
Topics live in `config.yaml → pillars`; add your own there.

Each caption = hook + body + 3–5 topical hashtags + brand hashtags. No links.

## Local commands
```bash
python main.py health            # status + upcoming posts
python main.py generate --count 3
python main.py deliver           # send new posts to Telegram
python main.py poll              # apply Approve/Reject taps once
python main.py schedule
python main.py bot               # continuous Telegram listener (optional)
```

## Secrets (GitHub → Settings → Secrets → Actions)
`GEMINI_API_KEY`, `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`

## Instant Telegram buttons (`worker/`)
A free Cloudflare Worker receives button taps through a Telegram webhook, answers in under a second,
and triggers `approve.yml` through GitHub `repository_dispatch`. Worker secrets: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ADMIN_CHAT_ID`, `WEBHOOK_SECRET`, `GITHUB_TOKEN` (fine-grained, this repo only, Contents: read & write).
To go back to hourly polling: call Telegram `deleteWebhook`.
