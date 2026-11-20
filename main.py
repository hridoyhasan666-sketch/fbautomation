"""
Archive Micro-Story CLI Management Console.
Unified controller for harvesting, generation, approval delivery, scheduling, and metrics.
"""

import sys
import argparse
from ops.health import HealthMonitor
from harvest.loc import LocHarvester
from generate.pipeline import StoryPipeline
from bot.telegram_bot import TelegramApprovalBot
from publish.schedule import MetaPublisher
from ops.metrics import MetricsHarvester
from learn.bandit import LearningLoop

from db.database import init_db, get_seed_stock_counts

def main():
    init_db()
    # Auto-seed starter pack if stock is empty
    if not get_seed_stock_counts():
        try:
            LocHarvester().import_curated_seeds_file("data/seeds_curated.json")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Archive Micro-Story Facebook Automation Engine")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Health command
    subparsers.add_parser("health", help="Check system status, keys, seed stock, and queue levels")

    # Harvest command
    p_harvest = subparsers.add_parser("harvest", help="Fetch pre-1930 newspaper items from Chronicling America")
    p_harvest.add_argument("--count", type=int, default=2, help="Number of seeds to harvest per format")

    # Import curated command
    p_import = subparsers.add_parser("import-curated", help="Import vetted seed cards from JSON")
    p_import.add_argument("--file", type=str, default="data/seeds_curated.json", help="Path to JSON file")

    # Generate command
    p_generate = subparsers.add_parser("generate", help="Draft, judge, and render posts")
    p_generate.add_argument("--format", type=str, default="", help="Specific format to generate, or empty for all")
    p_generate.add_argument("--count", type=int, default=1, help="Number of posts per format")

    # Deliver command
    subparsers.add_parser("deliver", help="Send pending posts to Telegram for approval")

    # Bot command
    subparsers.add_parser("bot", help="Run Telegram bot long-polling loop")

    # Schedule command
    subparsers.add_parser("schedule", help="Schedule approved posts on Facebook Graph API")

    # Metrics command
    subparsers.add_parser("metrics", help="Fetch 48-hour post insights and engagement scores")

    # Learn command
    subparsers.add_parser("learn", help="Run Thompson sampling bandit reweighting & golden example refresh")

    # Test-post command
    subparsers.add_parser("test-post", help="Phase 2 visibility test: post immediately to Facebook Page")

    args = parser.parse_args()

    if args.command == "health" or not args.command:
        HealthMonitor().print_diagnostics()

    elif args.command == "harvest":
        print("[CLI] Running Chronicling America Harvester...")
        h = LocHarvester()
        h.harvest_all_formats(seeds_per_format=args.count)

    elif args.command == "import-curated":
        h = LocHarvester()
        h.import_curated_seeds_file(args.file)

    elif args.command == "generate":
        pipeline = StoryPipeline()
        if args.format:
            pipeline.generate_single_slot(args.format)
        else:
            pipeline.generate_batch(count_per_format=args.count)

    elif args.command == "deliver":
        bot = TelegramApprovalBot()
        delivered = bot.deliver_all_pending()
        print(f"[CLI] Delivered {delivered} posts to Telegram for phone approval.")

    elif args.command == "bot":
        bot = TelegramApprovalBot()
        bot.run_polling()

    elif args.command == "schedule":
        pub = MetaPublisher()
        count = pub.run_scheduling_job()
        print(f"[CLI] Scheduled {count} posts to Meta Graph API.")

    elif args.command == "metrics":
        harvester = MetricsHarvester()
        harvester.sync_all_published_posts()

    elif args.command == "learn":
        loop = LearningLoop()
        loop.run_thompson_sampling()
        loop.refresh_golden_examples()
        print(loop.generate_weekly_report())

    elif args.command == "test-post":
        pub = MetaPublisher()
        pub.test_visibility_post()

if __name__ == "__main__":
    main()
