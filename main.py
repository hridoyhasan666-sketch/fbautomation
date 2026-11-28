"""
Sincerely Yours - Facebook content engine CLI.
generate -> deliver (Telegram) -> poll (approvals) -> schedule (Facebook) -> metrics/learn (weekly)
"""

import argparse
from db.database import init_db
from utils.config import CONFIG


def main():
    init_db()

    parser = argparse.ArgumentParser(description="Sincerely Yours Facebook content engine")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("health", help="Show configuration and queue status")
    p_gen = sub.add_parser("generate", help="Write, judge and render new posts")
    p_gen.add_argument("--count", type=int, default=CONFIG.get("generation", {}).get("daily_count", 3),
                       help="Number of posts to create")
    p_gen.add_argument("--format", type=str, default="", help="Force a format (e.g. then_vs_now)")
    sub.add_parser("deliver", help="Send new posts to Telegram for approval")
    sub.add_parser("poll", help="Process Telegram Approve/Reject presses once and exit")
    p_apply = sub.add_parser("apply", help="Apply one Approve/Reject tap (used by the webhook worker)")
    p_apply.add_argument("action", choices=["approve", "reject", "rewrite"])
    p_apply.add_argument("post_id")
    sub.add_parser("bot", help="Run the Telegram approval listener continuously")
    sub.add_parser("schedule", help="Schedule approved posts on Facebook at random daily slots")
    sub.add_parser("metrics", help="Pull engagement for published posts")
    sub.add_parser("learn", help="Reweight formats from engagement")
    sub.add_parser("test-post", help="Publish one immediate test post")

    args = parser.parse_args()

    if args.command in (None, "health"):
        from ops.health import HealthMonitor
        HealthMonitor().print_diagnostics()

    elif args.command == "generate":
        from generate.pipeline import StoryPipeline
        pipeline = StoryPipeline()
        made = sum(1 for _ in range(args.count) if pipeline.generate_single_slot(args.format or None))
        print(f"[CLI] Created {made}/{args.count} posts.")

    elif args.command == "deliver":
        from bot.telegram_bot import TelegramApprovalBot
        print(f"[CLI] Delivered {TelegramApprovalBot().deliver_all_pending()} posts to Telegram.")

    elif args.command == "poll":
        from bot.telegram_bot import TelegramApprovalBot
        TelegramApprovalBot().poll_once()

    elif args.command == "apply":
        from bot.telegram_bot import TelegramApprovalBot
        TelegramApprovalBot().apply_decision(args.action, args.post_id)
        if args.action == "approve":
            from publish.schedule import MetaPublisher
            from db.database import get_connection
            MetaPublisher().run_scheduling_job()
            with get_connection() as conn:
                row = conn.execute("SELECT status, scheduled_publish_time FROM posts WHERE post_id = ?",
                                   (args.post_id,)).fetchone()
            if row and row["status"] == "scheduled" and row["scheduled_publish_time"]:
                from datetime import datetime, timezone
                when = datetime.fromtimestamp(int(row["scheduled_publish_time"]), timezone.utc)
                TelegramApprovalBot().notify(
                    f"📅 {args.post_id} is scheduled on Facebook for {when:%a %d %b, %H:%M} UTC.")
            elif row and row["status"] == "approved":
                TelegramApprovalBot().notify(
                    f"{args.post_id}: approved, but no free slot yet - it will be scheduled automatically.")

    elif args.command == "bot":
        from bot.telegram_bot import TelegramApprovalBot
        TelegramApprovalBot().run_polling()

    elif args.command == "schedule":
        from publish.schedule import MetaPublisher
        print(f"[CLI] Scheduled {MetaPublisher().run_scheduling_job()} posts.")

    elif args.command == "metrics":
        from ops.metrics import MetricsHarvester
        MetricsHarvester().sync_all_published_posts()

    elif args.command == "learn":
        from learn.bandit import LearningLoop
        loop = LearningLoop()
        loop.run_thompson_sampling()
        loop.refresh_golden_examples()
        print(loop.generate_weekly_report())

    elif args.command == "test-post":
        from publish.schedule import MetaPublisher
        MetaPublisher().test_visibility_post()


if __name__ == "__main__":
    main()
