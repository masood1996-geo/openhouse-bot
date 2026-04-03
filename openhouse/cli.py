import os
import sys
import subprocess
import time
import webbrowser
import requests
import yaml

CONFIG_FILE = ".openhouse.yaml"

# ── Try to import questionary (arrow-key selection UI) ───────────────────────
try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
    STYLE = Style([
        ("qmark",        "fg:#00d7ff bold"),
        ("question",     "fg:#ffffff bold"),
        ("answer",       "fg:#00ff87 bold"),
        ("pointer",      "fg:#00d7ff bold"),
        ("highlighted",  "fg:#00d7ff bold"),
        ("selected",     "fg:#00ff87"),
        ("separator",    "fg:#444444"),
        ("instruction",  "fg:#888888"),
    ])
except ImportError:
    HAS_QUESTIONARY = False

# ── Yes/no helper ─────────────────────────────────────────────────────────────
YES_WORDS = {"y","yes","ya","ja","yep","yup","sure","ok","okay","yea"}
NO_WORDS  = {"n","no","nope","nein","na","nah"}

def ask_yes_no(prompt, default=False):
    if HAS_QUESTIONARY:
        ans = questionary.confirm(prompt, default=default, style=STYLE).ask()
        return ans if ans is not None else default
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {hint}: ").strip().lower()
        if raw == "":
            return default
        if raw in YES_WORDS:
            return True
        if raw in NO_WORDS:
            return False
        print("  Please answer yes (y) or no (n).")

def ask_select(prompt, choices, default=None):
    """Arrow-key selection menu."""
    if HAS_QUESTIONARY:
        return questionary.select(prompt, choices=choices, default=default, style=STYLE).ask()
    print(f"\n{prompt}")
    for i, c in enumerate(choices, 1):
        marker = " <-- default" if c == default else ""
        print(f"  {i}. {c}{marker}")
    while True:
        raw = input("  Enter number: ").strip()
        if raw == "" and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print("  Invalid choice.")

def ask_input(prompt, default=None, skip_hint=False):
    full_prompt = prompt
    if skip_hint:
        full_prompt += " (press Enter to skip)"
    if default:
        full_prompt += f" [{default}]"
    if HAS_QUESTIONARY:
        ans = questionary.text(full_prompt, default=default or "", style=STYLE).ask()
        return ans.strip() if ans else (default or "")
    val = input(f"{full_prompt}: ").strip()
    return val if val else (default or "")

def banner(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def section(text):
    print(f"\n┌{'─'*56}┐")
    print(f"│  {text:<54}│")
    print(f"└{'─'*56}┘")

# ── Live model fetchers ───────────────────────────────────────────────────────
PROVIDER_INFO = {
    "openrouter": {
        "label": "OpenRouter  (many models, generous free tier)",
        "url":   "https://openrouter.ai/keys",
        "fetch": lambda: _fetch_openrouter_models(),
    },
    "openai": {
        "label": "OpenAI  (GPT-4o, GPT-4o-mini)",
        "url":   "https://platform.openai.com/api-keys",
        "fetch": lambda: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "kilo": {
        "label": "KiloCode / Kilo AI  (Claude, Gemini, free credits)",
        "url":   "https://kilo.ai",
        "fetch": lambda: ["claude-sonnet-4-5", "claude-3-7-sonnet", "gemini-2.5-flash", "gpt-4o-mini"],
    },
    "anthropic": {
        "label": "Anthropic  (Claude models)",
        "url":   "https://console.anthropic.com",
        "fetch": lambda: ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    },
}

def _fetch_openrouter_models(limit=30, free_only=False):
    """Fetch live model list from OpenRouter (no auth needed)."""
    try:
        print("  Fetching live model list from OpenRouter...", end="", flush=True)
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=8)
        r.raise_for_status()
        models = r.json().get("data", [])
        # Sort by name, optionally filter free models
        result = []
        for m in models:
            mid = m.get("id", "")
            pricing = m.get("pricing", {})
            is_free = pricing.get("prompt") == "0" or ":free" in mid
            if free_only and not is_free:
                continue
            tag = "  [FREE]" if is_free else ""
            result.append(f"{mid}{tag}")
        print(f" {len(result)} models found.")
        return sorted(result)[:limit]
    except Exception as e:
        print(f" failed ({e}). Using defaults.")
        return ["google/gemini-2.5-flash", "openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3.3-70b-instruct:free"]

# ── Provider & model selection ────────────────────────────────────────────────
def select_provider_and_model():
    section("AI Provider & Model")
    print("  Use ↑↓ arrow keys to navigate, Enter to select.\n")

    provider_choices = [info["label"] for info in PROVIDER_INFO.values()]
    provider_choice  = ask_select("Select your AI provider:", provider_choices)

    # Map label back to key
    provider_key = None
    for key, info in PROVIDER_INFO.items():
        if info["label"] == provider_choice:
            provider_key = key
            break

    info = PROVIDER_INFO[provider_key]

    # Offer to open API key page
    if ask_yes_no(f"  Open {provider_key} key page in browser?", default=True):
        webbrowser.open(info["url"])
        input("  Press Enter when you have your API key ready...")

    api_key = ask_input(f"  Paste your {provider_key} API key")

    # Fetch live models
    print()
    models = info["fetch"]()

    if provider_key == "openrouter":
        show_free = ask_yes_no("  Show only FREE models?", default=False)
        if show_free:
            models = _fetch_openrouter_models(limit=50, free_only=True)

    models.append("[ Type a custom model ID ]")
    model_choice = ask_select("Select model:", models)

    if model_choice == "[ Type a custom model ID ]":
        model_choice = ask_input("  Enter model ID")

    # Strip the [FREE] tag if present
    model_id = model_choice.replace("  [FREE]", "").strip()

    return provider_key, api_key, model_id

# ── Telegram setup ────────────────────────────────────────────────────────────
def telegram_setup():
    section("Telegram Bot Setup")
    print("  Steps:")
    print("  1. Open Telegram → search @BotFather")
    print("  2. Send /newbot → follow instructions")
    print("  3. Copy the Bot Token\n")

    if ask_yes_no("  Open @BotFather in browser?", default=True):
        webbrowser.open("https://t.me/BotFather")
        input("  Press Enter once you have your Bot Token...")

    token = ask_input("  Paste your Telegram Bot Token")
    if not token:
        print("  [!] No token entered. Skipping Telegram.")
        return None, None

    bot_username = _get_bot_username(token)
    if bot_username:
        print(f"\n  Your bot: @{bot_username}")
        print("  Opening bot — please send it any message (e.g. hi)...")
        webbrowser.open(f"https://t.me/{bot_username}")
    else:
        print("  Could not look up bot. Open it in Telegram and send a message.")

    input("  Press Enter once you've sent your bot a message...")
    chat_id = _poll_for_chat_id(token)

    if chat_id:
        print(f"  [OK] Chat ID auto-detected: {chat_id}")
    else:
        print("  [!] Could not auto-detect Chat ID.")
        chat_id = ask_input("  Enter Chat ID manually", skip_hint=True)

    return token, chat_id

def _get_bot_username(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        d = r.json()
        if d.get("ok"):
            return d["result"].get("username")
    except Exception:
        pass
    return None

def _poll_for_chat_id(token, timeout=60):
    print(f"  Waiting for your message ({timeout}s)...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 5},
                timeout=10
            )
            d = r.json()
            if d.get("ok") and d["result"]:
                update = d["result"][0]
                chat_id = (
                    update.get("message", {}).get("chat", {}).get("id") or
                    update.get("channel_post", {}).get("chat", {}).get("id")
                )
                print(" got it!")
                return str(chat_id)
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(3)
    print()
    return None

# ── WhatsApp setup ────────────────────────────────────────────────────────────
def whatsapp_setup():
    section("WhatsApp Setup (CallMeBot)")
    print("  Free gateway, no account needed.")
    print("  1. Save +34 644 59 78 89 in your contacts")
    print("  2. Send:  I allow callmebot to send me messages")
    print("  3. You'll receive your API key on WhatsApp\n")

    if ask_yes_no("  Open CallMeBot setup page?", default=True):
        webbrowser.open("https://www.callmebot.com/blog/free-api-whatsapp-messages/")
        input("  Press Enter once you have your API key...")

    phone   = ask_input("  Your WhatsApp number (e.g. +4915112345678)")
    api_key = ask_input("  Your CallMeBot API key")
    return phone, api_key

# ── Main wizard ───────────────────────────────────────────────────────────────
def setup_wizard():
    banner("Welcome to OpenHouse Bot Setup!")

    config = {}

    # Provider & model
    provider, api_key, model = select_provider_and_model()
    config["ai_provider"] = provider
    config["ai_api_key"]  = api_key
    config["ai_model"]    = model

    # Location
    section("Search Location")
    config["city"]   = ask_input("City to search in (e.g. Berlin, Amsterdam, London)")
    config["radius"] = ask_input("Search radius in km", default="10")

    # Notifications
    section("Notifications")
    notif = ask_select(
        "How do you want to receive alerts?",
        ["telegram  — real-time push notifications (recommended)",
         "whatsapp  — via CallMeBot free gateway"],
    )
    config["notification_method"] = "telegram" if "telegram" in notif else "whatsapp"

    if config["notification_method"] == "telegram":
        token, chat_id = telegram_setup()
        config["telegram_bot_token"] = token or ""
        config["telegram_chat_id"]   = chat_id or ""
    else:
        phone, key = whatsapp_setup()
        config["whatsapp_number"]  = phone or ""
        config["whatsapp_api_key"] = key or ""

    # Apartment preferences
    section("Apartment Preferences")
    config["price_min"] = ask_input("Minimum monthly rent", skip_hint=True) or "0"
    config["price_max"] = ask_input("Maximum monthly rent", skip_hint=True) or "0"
    config["rooms_min"] = ask_input("Minimum number of rooms (e.g. 2)", skip_hint=True) or "0"

    print()
    config["exclude_swaps"] = ask_yes_no("Exclude apartment swaps (Tauschwohnung)?", default=True)
    config["search_agents"] = ask_yes_no("Search for local rental agents (agencies/brokers) too?", default=True)

    # Save
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"\n  [OK] Config saved to {CONFIG_FILE}")
    return config

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(CONFIG_FILE):
        config = setup_wizard()
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        print(f"\n  [INFO] Loaded config from {CONFIG_FILE}")
        if ask_yes_no("  Re-run setup wizard?", default=False):
            config = setup_wizard()

    print("\n  Starting OpenHouse Bot...")

    # Discover apartment portals
    try:
        from openhouse.ai_discovery import discover_providers
        urls = discover_providers(config)
        if not urls:
            print("  [!] No URLs found. Using built-in fallbacks.")
            urls = []
    except Exception as e:
        print(f"  [!] Discovery failed: {e}")
        urls = []

    # Launch crawler — auto-install any missing deps and retry once
    _launch_crawler(config, urls)

def _launch_crawler(config, urls, retried=False):
    try:
        from openhouse.crawler_runner import run_bot
        run_bot(config, urls)
    except ModuleNotFoundError as e:
        raw = str(e).replace("No module named ", "").strip("'").split(".")[0]
        # Map internal module names to pip package names
        pip_map = {
            "distutils":   "setuptools",
            "firebase_admin": "firebase-admin",
            "OpenHouse":   None,   # internal — not a pip package
            "flask_restful": "flask-restful",
            "ruamel":      "ruamel.yaml",
        }
        pkg = pip_map.get(raw, raw.replace("_", "-"))
        if pkg is None:
            print(f"\n  [ERROR] Internal import error: {e}")
            print("  This is a bug in the package — please report it.")
            sys.exit(1)
        if retried:
            print(f"\n  [ERROR] Still missing '{pkg}' after install attempt.")
            print(f"  Try manually:  pip install {pkg}")
            sys.exit(1)
        print(f"\n  [!] Missing dependency '{pkg}'. Installing now...")
        rc = subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"]).returncode
        if rc != 0:
            print(f"  [ERROR] Failed to install {pkg}.")
            sys.exit(1)
        print(f"  [OK] Installed {pkg}. Retrying...\n")
        _launch_crawler(config, urls, retried=True)

if __name__ == "__main__":
    main()
