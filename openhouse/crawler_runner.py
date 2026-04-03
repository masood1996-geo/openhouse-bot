import time
import threading
import logging
import yaml
from pathlib import Path

from openhouse.config import Config
from openhouse.heartbeat import Heartbeat
from openhouse.idmaintainer import IdMaintainer
from openhouse.hunter import Hunter
from openhouse.time_utils import get_random_time_jitter

logger = logging.getLogger(__name__)

def _generate_openhouse_config(user_prefs, ai_urls):
    """
    Generate a dynamic OpenHouse config dictionary from user preferences
    and the AI discovered URLs.
    """
    config = {
        "database_location": ".",
        "notifiers": [user_prefs.get("notification_method", "telegram")],
        "urls": ai_urls,
        "target_city": user_prefs.get("city", ""),
        "ai_provider": user_prefs.get("ai_provider", ""),
        "ai_api_key": user_prefs.get("ai_api_key", ""),
        "ai_model": user_prefs.get("ai_model", ""),
        "loop": {
            "active": True,
            "sleeping_time": 600,
            "random_jitter": True,
        },
        "filters": {
            "max_price": int(user_prefs.get("price_max", 0)) or None,
            "min_rooms": int(user_prefs.get("rooms_min", 0)) or None,
            "exclude_swaps": user_prefs.get("exclude_swaps", True),
        }
    }
    
    if user_prefs.get("notification_method") == "telegram":
        config["telegram"] = {
            "bot_token": user_prefs.get("telegram_bot_token", ""),
            "receiver_ids": [int(user_prefs.get("telegram_chat_id", 0))]
        }
    elif user_prefs.get("notification_method") == "whatsapp":
        config["whatsapp"] = {
            "number": user_prefs.get("whatsapp_number", "")
        }
        
    return config

def run_bot(user_prefs, ai_urls):
    """
    Initializes the bot with dynamic configuration, runs the first crawl synchronously,
    then detaches to a background thread to crawl continuously.
    """
    print("[*] Configuring openhouse background crawler...")
    
    # Generate the yaml structure for OpenHouse Config
    dynamic_config = _generate_openhouse_config(user_prefs, ai_urls)
    
    with open("bot_runtime_config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(dynamic_config, f)
        
    config = Config("bot_runtime_config.yaml")
    config.init_searchers()

    # Diagnostics: show what was loaded
    target_urls = config.target_urls()
    print(f"\n[*] Loaded {len(target_urls)} target URLs:")
    for u in target_urls:
        print(f"    → {u}")
    notifiers_list = config.notifiers()
    print(f"[*] Active notifiers: {notifiers_list}")
    if 'telegram' in notifiers_list:
        print(f"    → Telegram bot token: ...{str(config.telegram_bot_token() or '')[-8:]}")
        print(f"    → Telegram receivers: {config.telegram_receiver_ids()}")

    # Remove stale DB so first run sends all found apartments
    import os
    db_dir = config.database_location()
    db_path = f'{db_dir}/processed_ids.db'
    if os.path.exists(db_path):
        print(f"[*] Clearing old listing DB for fresh results...")
        os.remove(db_path)
    
    # 1. Run the initial crawl logic inline
    print("\n[*] Starting initial crawl...")
    id_watch = IdMaintainer(f'{db_dir}/processed_ids.db')
    hunter = Hunter(config, id_watch)
    hunter.hunt_flats()
    
    # 2. Launch background monitoring
    def _background_loop():
        print("[*] Crawler running in background...")
        heartbeat = Heartbeat(config, 3600)
        counter = 1
        while config.loop_is_active():
            counter += 1
            counter = heartbeat.send_heartbeat(counter)
            
            sleep_period = config.loop_period_seconds()
            if config.random_jitter_enabled():
                sleep_period = get_random_time_jitter(sleep_period)
                
            time.sleep(sleep_period)
            hunter.hunt_flats()

    bg_thread = threading.Thread(target=_background_loop, daemon=True)
    bg_thread.start()
    
    print("\n" + "="*60)
    print("OpenHouse Bot is now active and hunting properties in the background.")
    print("You can close this window if it's a server, or leave it open to keep the thread alive.")
    print("="*60)
    
    # Keep the main process alive since python exit kills daemon threads
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping OpenHouse Bot...")
