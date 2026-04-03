#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AntiGravity Finder Bot — AI-powered Berlin apartment hunting Telegram bot.
Combines OpenHouse's crawling engine with an AI conversational interface.

IMPROVEMENTS adopted from GitHub research:
- Auto-restart with exponential backoff (never dies)
- Per-crawler error isolation (one crash doesn't kill the rest)
- Health/status monitoring via /status command
- Network retry with backoff library
- Vonovia crawler added

Run: python ai_telegram_bot.py
"""

import os
import sys
import asyncio
import logging
import traceback
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import backoff
from urllib.parse import urlparse

# Add parent to path for OpenHouse imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openhouse.config import Config
from openhouse.hunter import Hunter
from openhouse.idmaintainer import IdMaintainer
from openhouse.user_prefs import UserPrefs
from openhouse.ai_brain import AIBrain
from openhouse.logging import logger
from openhouse.smart_crawler import smart_crawl_all, smart_crawl_url
from openhouse.learning_memory import LearningMemory

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
KILOCODE_API_KEY = os.getenv("KILOCODE_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CRAWL_INTERVAL_SECONDS = int(os.getenv("CRAWL_INTERVAL_SECONDS", "600"))  # 10 min
CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yaml")

# ─── Global State ────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
user_prefs = UserPrefs(os.path.join(BASE_DIR, "user_prefs.json"))
# AI brain: prefers OpenRouter, falls back to Kilo Code
ai_brain = AIBrain(KILOCODE_API_KEY) if (OPENROUTER_API_KEY or KILOCODE_API_KEY) else None
registered_chat_ids = set()

# Learning memory for smart crawler
learning_memory = LearningMemory()

ALLOWED_SMART_CRAWL_DOMAINS = {
    'vonovia.de', 'deutsche-wohnen.com', 'berlinovo.de',
    'heimstaden.com', 'grandcityproperty.de', 'covivio.eu',
    'charlotte1907.de', '1892.de', 'wunderflats.com',
    'housinganywhere.com', 'propotsdam.de',
}

# Health tracking
BOT_START_TIME = None
CRAWL_STATS = {
    'total_crawls': 0,
    'successful_crawls': 0,
    'total_listings_found': 0,
    'total_messages_sent': 0,
    'last_crawl_time': None,
    'last_crawl_listings': 0,
    'crawler_errors': {},
    'consecutive_failures': 0,
}

# Store chat IDs persistently
CHAT_IDS_FILE = os.path.join(BASE_DIR, "chat_ids.txt")


def load_chat_ids():
    """Load registered chat IDs from file"""
    global registered_chat_ids
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    registered_chat_ids.add(int(line))


def save_chat_ids():
    """Save registered chat IDs to file"""
    with open(CHAT_IDS_FILE, 'w') as f:
        for cid in registered_chat_ids:
            f.write(f"{cid}\n")


# ─── Telegram Command Handlers ───────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = update.effective_chat.id
    registered_chat_ids.add(chat_id)
    save_chat_ids()

    welcome = (
        "Welcome to AntiGravity Finder Bot!\n\n"
        "I hunt Berlin apartments for you 24/7.\n\n"
        "What I can do:\n"
        "- Scrape 10+ Berlin housing portals every 10 minutes\n"
        "- Understand natural language -- just chat with me!\n"
        "- Manage your search preferences\n"
        "- Send instant notifications for new listings\n"
        "- AI agent can navigate complex sites autonomously\n\n"
        "Commands:\n"
        "/prefs -- View your current search preferences\n"
        "/search -- Trigger a manual search now\n"
        "/smartsearch <url> -- AI agent scrapes any URL\n"
        "/learn -- Show what the AI agent has learned\n"
        "/status -- Check bot health and stats\n"
        "/pause -- Pause notifications\n"
        "/resume -- Resume notifications\n"
        "/reset -- Reset conversation with AI\n"
        "/help -- Show this help message\n\n"
        "Or just chat with me! Try:\n"
        "  'Set max rent to 900 euros'\n"
        "  'I want 2+ rooms in Kreuzberg'\n"
        "  'What are the best neighborhoods?'\n\n"
        f"Your chat ID {chat_id} has been registered for notifications!"
    )
    await update.message.reply_text(welcome)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await cmd_start(update, context)


async def cmd_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /prefs command — show current preferences"""
    summary = user_prefs.get_summary()
    try:
        await update.message.reply_text(summary, parse_mode='Markdown')
    except Exception:
        await update.message.reply_text(summary)


async def cmd_smartsearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /smartsearch <url> command — AI agent scrapes any URL"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /smartsearch <url>\n\n"
            "Example: /smartsearch https://www.vonovia.de/...\n\n"
            "The AI agent will autonomously navigate the site, "
            "interact with forms/dropdowns, and extract apartment listings."
        )
        return

    url = context.args[0]
    domain = urlparse(url).netloc.replace('www.', '')
    
    if domain not in ALLOWED_SMART_CRAWL_DOMAINS:
        await update.message.reply_text(
            f"Sorry, I can only crawl trusted housing portals. "
            f"'{domain}' is not in my allowlist. "
            f"Contact an admin to add it."
        )
        return

    await update.message.reply_text(
        f"AI Agent starting to explore:\n{url}\n\n"
        "This may take 1-3 minutes. The agent will navigate the page, "
        "interact with elements, and extract listings..."
    )

    try:
        listings = await smart_crawl_url(url)
        if listings:
            await update.message.reply_text(
                f"AI Agent found {len(listings)} listing(s)! Sending now..."
            )
            for listing in listings:
                msg = format_listing(listing)
                try:
                    await update.message.reply_text(msg)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error("Failed to send smart listing: %s", e)
        else:
            await update.message.reply_text(
                "AI Agent couldn't find listings on that page. "
                "Try a different URL or check if the site requires login."
            )
    except Exception as e:
        logger.error("Smart search error: %s", traceback.format_exc())
        await update.message.reply_text(f"AI Agent error: {str(e)[:200]}")


async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /learn command — show what the AI agent has learned"""
    stats = learning_memory.get_stats()
    total = stats['total_strategies']
    positive = stats['positive_strategies']

    if total == 0:
        await update.message.reply_text(
            "The AI Agent hasn't learned any strategies yet.\n"
            "It will start learning after crawling sites.\n\n"
            "Use /smartsearch <url> to teach it a new site!"
        )
        return

    text = (
        f"=== AI Agent Learning Memory ===\n\n"
        f"Total strategies: {total}\n"
        f"Working strategies: {positive}\n\n"
        f"--- Per-Site Stats ---\n"
    )
    for site, info in stats.get('sites', {}).items():
        score = info.get('score', 0)
        successes = info.get('successes', 0)
        failures = info.get('failures', 0)
        status_icon = '+' if score > 0 else ('-' if score < 0 else '=')
        text += f"  [{status_icon}] {site}: score={score}, ok={successes}, fail={failures}\n"

    await update.message.reply_text(text)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command — trigger manual crawl"""
    await update.message.reply_text("Starting manual search... This may take a minute.")
    try:
        new_listings = run_crawl()
        if new_listings:
            await update.message.reply_text(f"Found {len(new_listings)} new listing(s)! Sending now...")
            for listing in new_listings:
                msg = format_listing(listing)
                try:
                    await update.message.reply_text(msg)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error("Failed to send listing: %s", e)
        else:
            await update.message.reply_text("No new listings found right now. I'll keep checking!")
    except Exception as e:
        logger.error("Manual search error: %s", traceback.format_exc())
        await update.message.reply_text(f"Search error: {str(e)}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show bot health and crawl stats"""
    uptime = "Unknown"
    if BOT_START_TIME:
        delta = datetime.now() - BOT_START_TIME
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {seconds}s"

    last_crawl = CRAWL_STATS['last_crawl_time']
    if last_crawl:
        last_crawl_str = last_crawl.strftime("%H:%M:%S")
        mins_ago = int((datetime.now() - last_crawl).total_seconds() / 60)
        last_crawl_str += f" ({mins_ago}m ago)"
    else:
        last_crawl_str = "Not yet"

    # Crawler error summary
    error_lines = []
    for crawler_name, count in CRAWL_STATS['crawler_errors'].items():
        error_lines.append(f"  {crawler_name}: {count} errors")

    status = (
        f"=== AntiGravity Finder Bot Status ===\n\n"
        f"Uptime: {uptime}\n"
        f"Registered users: {len(registered_chat_ids)}\n"
        f"AI Brain: {'Active' if ai_brain else 'Disabled'}\n\n"
        f"--- Crawl Stats ---\n"
        f"Total crawl cycles: {CRAWL_STATS['total_crawls']}\n"
        f"Successful crawls: {CRAWL_STATS['successful_crawls']}\n"
        f"Total listings found: {CRAWL_STATS['total_listings_found']}\n"
        f"Total messages sent: {CRAWL_STATS['total_messages_sent']}\n"
        f"Last crawl: {last_crawl_str}\n"
        f"Last crawl listings: {CRAWL_STATS['last_crawl_listings']}\n"
        f"Consecutive failures: {CRAWL_STATS['consecutive_failures']}\n"
    )
    if error_lines:
        status += f"\n--- Crawler Errors ---\n" + "\n".join(error_lines)

    await update.message.reply_text(status)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pause command"""
    user_prefs.set('notifications_active', False)
    await update.message.reply_text("Notifications paused. Use /resume to start again.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume command"""
    user_prefs.set('notifications_active', True)
    await update.message.reply_text("Notifications resumed! I'll send new listings as I find them.")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reset command — reset AI conversation"""
    if ai_brain:
        ai_brain.reset_conversation()
    await update.message.reply_text("Conversation reset! Start fresh.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages — route to AI brain"""
    chat_id = update.effective_chat.id
    registered_chat_ids.add(chat_id)
    save_chat_ids()

    user_text = update.message.text
    if not user_text:
        return

    if not ai_brain:
        await update.message.reply_text(
            "AI brain is not configured (missing KILOCODE_API_KEY).\n"
            "Use /prefs to view preferences and /help for commands."
        )
        return

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    # Get AI response
    prefs_summary = user_prefs.get_summary()
    response_text, action = ai_brain.chat(user_text, prefs_summary)

    # Handle action if present
    if action and action.get('action') == 'update_prefs':
        updates = action.get('updates', {})
        if updates:
            user_prefs.update(updates)
            logger.info("Preferences updated via AI: %s", updates)

    # Send response
    if response_text:
        # Split long messages (Telegram limit is 4096 chars)
        for i in range(0, len(response_text), 4000):
            chunk = response_text[i:i+4000]
            try:
                await update.message.reply_text(chunk, parse_mode='Markdown')
            except Exception:
                # Fallback without markdown if parsing fails
                await update.message.reply_text(chunk)


# ─── Crawl Engine ────────────────────────────────────────────────────

def get_config():
    """Load OpenHouse config"""
    config_path = os.path.join(BASE_DIR, CONFIG_FILE)
    if os.path.exists(config_path):
        config = Config(config_path)
    else:
        config = Config()

    # Override filters from user preferences
    filter_dict = user_prefs.to_filter_dict()
    if filter_dict:
        existing_filters = config.config.get('filters', {}) or {}
        existing_filters.update(filter_dict)
        config.config['filters'] = existing_filters

    config.init_searchers()
    return config


def run_crawl():
    """Run a single crawl cycle and return new listings.
    Uses a CUSTOM processor chain that skips OpenHouse's broken
    built-in SenderTelegram (which has no receiver_ids configured).

    Each crawler is isolated — if one crashes, the rest continue.
    Adopted from EnXan/immo_alert_berlin's orchestrator pattern.
    """
    try:
        config = get_config()
        db_path = os.path.join(BASE_DIR, 'processed_ids.db')
        id_watch = IdMaintainer(db_path)
        hunter = Hunter(config, id_watch)

        # Build custom chain: save IDs + filter only, NO send_messages()
        from openhouse.filter import Filter as FlatFilter
        from openhouse.processor import ProcessorChain

        filter_set = FlatFilter.builder() \
                           .read_config(config) \
                           .filter_already_seen(id_watch) \
                           .build()

        processor_chain = ProcessorChain.builder(config) \
                                        .save_all_exposes(id_watch) \
                                        .apply_filter(filter_set) \
                                        .build()

        # Crawl with per-crawler error isolation
        all_exposes = []
        for searcher in config.searchers():
            for url in config.target_urls():
                try:
                    results = list(searcher.crawl(url, max_pages=None))
                    if results:
                        all_exposes.extend(results)
                        logger.info("Crawler %s found %d results for %s",
                                   type(searcher).__name__, len(results),
                                   url[:60])
                except Exception as e:
                    crawler_name = type(searcher).__name__
                    logger.error("Crawler %s FAILED on %s: %s",
                               crawler_name, url[:60], str(e)[:200])
                    CRAWL_STATS['crawler_errors'][crawler_name] = \
                        CRAWL_STATS['crawler_errors'].get(crawler_name, 0) + 1

        # Process through filter chain
        result = []
        for expose in processor_chain.process(iter(all_exposes)):
            logger.info('New listing: %s | %s | %s',
                       expose.get('title', '?'),
                       expose.get('price', '?'),
                       expose.get('url', '?'))
            result.append(expose)

        return result
    except Exception as e:
        logger.error("Crawl error: %s\n%s", e, traceback.format_exc())
        return []


def format_listing(listing: dict) -> str:
    """Format a listing for Telegram display — uses plain text to avoid
    Telegram Markdown parse errors that silently kill messages."""
    title = listing.get('title', 'N/A')
    rooms = listing.get('rooms', 'N/A')
    size = listing.get('size', 'N/A')
    price = listing.get('price', 'N/A')
    url = listing.get('url', '')
    address = listing.get('address', 'N/A')
    crawler = listing.get('crawler', 'Unknown')

    msg = (
        f"{'='*40}\n"
        f"APARTMENT: {title}\n"
        f"{'='*40}\n"
        f"Source: {crawler}\n"
        f"Address: {address}\n"
        f"Rooms: {rooms}\n"
        f"Size: {size}\n"
        f"Price: {price}\n\n"
        f"Link: {url}"
    )
    return msg


# ─── Background Crawl Job ────────────────────────────────────────────

async def crawl_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job that runs periodically to crawl for new listings.
    Fully isolated — never raises, never kills the bot."""
    if not user_prefs.get('notifications_active', True):
        logger.debug("Notifications paused, skipping crawl.")
        return

    if not registered_chat_ids:
        logger.debug("No registered chat IDs, skipping notifications.")
        return

    logger.info("Running scheduled crawl at %s", datetime.now().strftime("%H:%M:%S"))
    CRAWL_STATS['total_crawls'] += 1

    try:
        # Phase 1: Traditional OpenHouse crawlers
        new_listings = run_crawl()

        # Phase 2: Smart AI agent crawlers (run every 3rd cycle to save API calls)
        smart_listings = []
        if CRAWL_STATS['total_crawls'] % 3 == 0:
            try:
                logger.info("Running smart AI crawler (every 3rd cycle)...")
                smart_listings = await smart_crawl_all()
                if smart_listings:
                    # Deduplicate by URL
                    existing_urls = {l.get('url', '') for l in new_listings}
                    for sl in smart_listings:
                        if sl.get('url', '') not in existing_urls:
                            new_listings.append(sl)
                            existing_urls.add(sl.get('url', ''))
            except Exception as e:
                logger.error("Smart crawl failed (non-critical): %s", str(e)[:200])

        CRAWL_STATS['last_crawl_time'] = datetime.now()
        CRAWL_STATS['last_crawl_listings'] = len(new_listings) if new_listings else 0

        if new_listings:
            CRAWL_STATS['successful_crawls'] += 1
            CRAWL_STATS['consecutive_failures'] = 0
            CRAWL_STATS['total_listings_found'] += len(new_listings)
            logger.info("Found %d new listing(s) (%d smart), sending to %d user(s)",
                       len(new_listings), len(smart_listings),
                       len(registered_chat_ids))

            sent_count = 0
            for listing in new_listings:
                msg = format_listing(listing)
                for chat_id in registered_chat_ids:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg
                        )
                        sent_count += 1
                    except Exception as e:
                        logger.error("FAILED to send to %s: %s", chat_id, e)
                # Rate limit protection
                await asyncio.sleep(0.5)

            CRAWL_STATS['total_messages_sent'] += sent_count
            logger.info("Crawl cycle complete: %d messages sent", sent_count)
        else:
            CRAWL_STATS['successful_crawls'] += 1
            CRAWL_STATS['consecutive_failures'] = 0
            logger.info("No new listings found this cycle.")

    except Exception as e:
        CRAWL_STATS['consecutive_failures'] += 1
        logger.error("Scheduled crawl error (failure #%d): %s",
                    CRAWL_STATS['consecutive_failures'],
                    traceback.format_exc())


# ─── Main with Auto-Restart ──────────────────────────────────────────

def run_bot():
    """Single run of the Telegram bot polling loop."""
    global BOT_START_TIME
    BOT_START_TIME = datetime.now()

    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # Load saved chat IDs
    load_chat_ids()

    logger.info("=" * 60)
    logger.info("AntiGravity Finder Bot")
    logger.info("=" * 60)
    logger.info("Telegram: @antigravityfinder_bot")
    if OPENROUTER_API_KEY:
        logger.info("AI Brain: nemotron-3-super-120b via OpenRouter")
    elif KILOCODE_API_KEY:
        logger.info("AI Brain: Kimi 2.5 via Kilo Code")
    else:
        logger.info("AI Brain: Not configured")
    logger.info("Crawl interval: %ds (%d min)", CRAWL_INTERVAL_SECONDS, CRAWL_INTERVAL_SECONDS // 60)
    logger.info("Registered users: %d", len(registered_chat_ids))
    logger.info("=" * 60)

    # Build the application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("prefs", cmd_prefs))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("smartsearch", cmd_smartsearch))
    app.add_handler(CommandHandler("learn", cmd_learn))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("reset", cmd_reset))

    # Register message handler (catch-all for AI chat)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule background crawl job
    job_queue = app.job_queue
    job_queue.run_repeating(
        crawl_job,
        interval=CRAWL_INTERVAL_SECONDS,
        first=30  # First crawl 30 seconds after startup
    )

    # Run the bot
    app.run_polling(drop_pending_updates=True)


def main():
    """Main entry point with auto-restart loop.
    The bot will NEVER permanently die — it restarts with exponential backoff.
    Inspired by production patterns from immo_alert_berlin and OpenHouse.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env file!")
        return

    restart_count = 0
    max_backoff = 300  # Max 5 minutes between restarts

    while True:
        try:
            logger.info("Starting bot (attempt #%d)...", restart_count + 1)
            run_bot()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C)")
            break
        except SystemExit:
            logger.info("Bot received SystemExit")
            break
        except Exception as e:
            restart_count += 1
            # Exponential backoff: 5s, 10s, 20s, 40s, ... up to max_backoff
            wait_time = min(5 * (2 ** (restart_count - 1)), max_backoff)
            logger.error(
                "Bot crashed (attempt #%d): %s\n"
                "Restarting in %d seconds...",
                restart_count, str(e), wait_time
            )
            logger.error(traceback.format_exc())
            time.sleep(wait_time)


if __name__ == "__main__":
    main()
