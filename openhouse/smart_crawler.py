"""Smart Crawler — AI-powered web agent using browser-use + OpenRouter API.

Uses an LLM (liquid/lfm-2.5-1.2b-thinking:free via OpenRouter) to autonomously
navigate complex websites: click dropdowns, fill forms, and extract apartment
listings from sites that can't be scraped with simple HTML parsing.

Features:
- Self-learning via LearningMemory (strategy caching with scoring)
- Deep crawling: follows subpage links to discover listing pages
- Expanded site list from Berlin makler/agents/providers directory
"""
import asyncio
import json
import os
import re
import traceback
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

from dotenv import load_dotenv
from openhouse.logging import logger
from openhouse.learning_memory import LearningMemory

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
KILOCODE_API_KEY = os.getenv("KILOCODE_API_KEY", "")

# Use OpenRouter if available, fall back to Kilo Code
if OPENROUTER_API_KEY:
    SMART_API_KEY = OPENROUTER_API_KEY
    SMART_BASE_URL = "https://openrouter.ai/api/v1"
    SMART_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
    logger.info("SmartCrawler: Using OpenRouter (nemotron-3-super-120b:free)")
else:
    SMART_API_KEY = KILOCODE_API_KEY
    SMART_BASE_URL = "https://api.kilo.ai/api/gateway"
    SMART_MODEL = "minimax/minimax-m2.5:free"
    logger.info("SmartCrawler: Using Kilo Code (minimax-m2.5:free)")

# ─── Expanded Smart Crawl Sites ─────────────────────────────────────
# Sites that need AI agent (forms, JS rendering, complex navigation)
# Derived from berlin_makler_agents_providers.md
SMART_CRAWL_SITES = [
    # ── Major Private Housing Companies ──
    {
        "key": "vonovia_berlin",
        "url": "https://www.vonovia.de/zuhause-finden/immobilien?rentType=miete&city=Berlin&immoType=wohnung&priceMax=700",
        "task": "Find all rental apartments listed on this Vonovia Berlin search page. Extract title, address, rooms, size, price, URL for each.",
        "deep_crawl": True,
    },
    {
        "key": "deutsche_wohnen",
        "url": "https://www.deutsche-wohnen.com/mieten/wohnungssuche",
        "task": "Search for rental apartments in Berlin. Use any filters/dropdowns to select Berlin. Extract title, address, rooms, size, price, URL for each listing.",
        "deep_crawl": True,
    },
    {
        "key": "berlinovo",
        "url": "https://www.berlinovo.de/en/apartment",
        "task": "Find all available apartments for rent. Extract title, address, rooms, size, price, URL for each.",
        "deep_crawl": False,
    },
    {
        "key": "heimstaden_berlin",
        "url": "https://www.heimstaden.com/de/wohnungssuche/",
        "task": "Search for rental apartments in Berlin. Use filters to select Berlin. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": True,
    },
    {
        "key": "grand_city_property",
        "url": "https://www.grandcityproperty.de/wohnungssuche",
        "task": "Find rental apartments in Berlin. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": True,
    },
    {
        "key": "covivio",
        "url": "https://www.covivio.eu/de/mieten/",
        "task": "Find rental apartments in Berlin from Covivio. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": True,
    },

    # ── Housing Cooperatives (selected large ones) ──
    {
        "key": "charlottenburger_bg",
        "url": "https://www.charlotte1907.de/wohnungssuche/",
        "task": "Find available apartments from Charlottenburger Baugenossenschaft. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": False,
    },
    {
        "key": "1892_coop",
        "url": "https://www.1892.de/wohnen/wohnungsangebote/",
        "task": "Find available apartment listings from this cooperative. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": False,
    },

    # ── Furnished & Expat Platforms ──
    {
        "key": "wunderflats",
        "url": "https://www.wunderflats.com/en/furnished-apartments/berlin",
        "task": "Find furnished apartments in Berlin. Extract title, address, rooms, size, monthly price, URL.",
        "deep_crawl": False,
    },
    {
        "key": "housinganywhere",
        "url": "https://www.housinganywhere.com/s/Berlin--Germany",
        "task": "Find rental apartments in Berlin. Extract title, address/location, rooms, size, monthly price, URL.",
        "deep_crawl": False,
    },

    # ── Potsdam & Brandenburg ──
    {
        "key": "propotsdam",
        "url": "https://www.propotsdam.de/wohnen/wohnungssuche/",
        "task": "Find available apartments in Potsdam. Extract title, address, rooms, size, price, URL.",
        "deep_crawl": True,
    },
]

# ─── Learning Memory ─────────────────────────────────────────────────
memory = LearningMemory()


def _extract_listings_from_text(text: str) -> List[Dict]:
    """Extract structured listing data from LLM agent output text."""
    listings = []

    # Try to find JSON arrays in the text
    json_patterns = [
        r'```json\s*\n?([\s\S]*?)\n?\s*```',  # JSON in code fences
        r'\[[\s\S]*?\]',  # Any JSON array
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            listing = _normalize_listing(item)
                            if listing:
                                listings.append(listing)
                    if listings:
                        return listings
            except json.JSONDecodeError:
                continue

    # Fallback: try to parse individual JSON objects
    obj_pattern = r'\{[^{}]*(?:"title"|"address"|"price"|"url")[^{}]*\}'
    for match in re.findall(obj_pattern, text):
        try:
            item = json.loads(match)
            listing = _normalize_listing(item)
            if listing:
                listings.append(listing)
        except json.JSONDecodeError:
            continue

    return listings


def _normalize_listing(item: dict) -> Optional[Dict]:
    """Normalize a raw listing dict into our standard format."""
    if not isinstance(item, dict):
        return None

    title = (item.get('title') or item.get('name') or
             item.get('heading') or item.get('description') or 'Unknown')
    address = (item.get('address') or item.get('location') or
               item.get('street') or 'N/A')
    rooms = item.get('rooms') or item.get('num_rooms') or item.get('zimmer') or 'N/A'
    size = item.get('size') or item.get('area') or item.get('sqm') or 'N/A'
    price = (item.get('price') or item.get('rent') or
             item.get('monthly_rent') or item.get('miete') or 'N/A')
    url = item.get('url') or item.get('link') or item.get('href') or ''

    if title == 'Unknown' and not url:
        return None

    return {
        'title': str(title),
        'address': str(address),
        'rooms': str(rooms),
        'size': str(size),
        'price': str(price),
        'url': str(url),
        'crawler': 'SmartAgent',
    }


def _extract_subpage_urls(text: str, base_url: str) -> List[str]:
    """Extract discovered subpage URLs from agent output for deep crawling."""
    urls = []
    # Find URLs in the text
    url_pattern = r'https?://[^\s<>"\')\]]+(?:/[^\s<>"\')\]]*)*'
    found = re.findall(url_pattern, text)
    base_domain = urlparse(base_url).netloc

    for u in found:
        parsed = urlparse(u)
        # Only keep URLs from the same domain
        if parsed.netloc == base_domain and u != base_url:
            # Filter for likely listing/apartment pages
            path_lower = parsed.path.lower()
            listing_keywords = [
                'wohnung', 'apartment', 'listing', 'expose',
                'mieten', 'rental', 'angebot', 'objekt',
                'immobilie', 'detail', 'offer', 'property',
            ]
            if any(kw in path_lower for kw in listing_keywords):
                urls.append(u)

    return list(set(urls))[:20]  # Cap at 20 subpages


async def smart_crawl_site(site_config: dict) -> List[Dict]:
    """Crawl a single site using the browser-use AI agent.

    Supports deep crawling: if the agent finds subpage links,
    it can follow them to extract more listing details.
    """
    site_key = site_config['key']
    url = site_config['url']
    task = site_config['task']
    deep_crawl = site_config.get('deep_crawl', False)

    logger.info("SmartCrawl: Starting '%s' at %s (deep=%s)",
                site_key, url[:80], deep_crawl)

    try:
        from langchain_openai import ChatOpenAI
        from browser_use import Agent

        # Initialize LLM
        extra_headers = {}
        if OPENROUTER_API_KEY:
            extra_headers = {
                "HTTP-Referer": "https://github.com/antigravity-finder",
                "X-Title": "AntiGravity Finder Bot",
            }

        llm = ChatOpenAI(
            model=SMART_MODEL,
            base_url=SMART_BASE_URL,
            api_key=SMART_API_KEY,
            temperature=0.1,
            max_tokens=4096,
            default_headers=extra_headers if extra_headers else None,
        )

        # Check for learned strategy
        replay_hint = memory.generate_replay_prompt(site_key)

        # Build task prompt
        full_task = f"Go to {url}\n\n{task}\n\n"
        if replay_hint:
            full_task += f"HINT from previous successful visit:\n{replay_hint}\n\n"

        if deep_crawl:
            full_task += (
                "DEEP CRAWL MODE: Also look for links to individual listing pages "
                "or additional search result pages. If you find pagination or "
                "'next page' buttons, try to get listings from multiple pages. "
                "Include the full URLs of any listing detail pages you find.\n\n"
            )

        full_task += (
            "IMPORTANT: Return ONLY a JSON array of objects with these keys: "
            "title, address, rooms, size, price, url. "
            "Do not include any other text before or after the JSON."
        )

        # Run agent
        agent = Agent(
            task=full_task,
            llm=llm,
            use_vision=False,
            max_actions_per_step=5,
        )

        result = await agent.run(max_steps=15)

        # Extract result text
        result_text = ""
        if hasattr(result, 'final_result') and result.final_result:
            result_text = str(result.final_result)
        elif hasattr(result, 'history') and result.history:
            for msg in reversed(result.history):
                if hasattr(msg, 'result') and msg.result:
                    result_text = str(msg.result)
                    break

        if not result_text:
            result_text = str(result)

        logger.info("SmartCrawl: Result for '%s': %d chars", site_key, len(result_text))

        # Parse listings
        listings = _extract_listings_from_text(result_text)

        # Deep crawl: extract and save discovered subpage URLs
        if deep_crawl and result_text:
            subpage_urls = _extract_subpage_urls(result_text, url)
            if subpage_urls:
                logger.info("SmartCrawl: Deep crawl found %d subpage URLs for '%s'",
                           len(subpage_urls), site_key)
                # Save discovered URLs in the strategy for future 1-shot searching
                memory.save_discovered_urls(site_key, subpage_urls)

        if listings:
            logger.info("SmartCrawl: Found %d listings from '%s'",
                       len(listings), site_key)
            memory.save_strategy(
                site_key=site_key,
                task_description=task,
                extraction_prompt=full_task,
                results_count=len(listings),
            )
        else:
            logger.warning("SmartCrawl: No listings from '%s'", site_key)
            memory.record_failure(site_key)

        return listings

    except ImportError as e:
        logger.error("SmartCrawl: Missing dependency: %s", e)
        return []
    except Exception as e:
        logger.error("SmartCrawl: Error on '%s': %s\n%s",
                    site_key, str(e)[:200], traceback.format_exc())
        memory.record_failure(site_key)
        return []


async def smart_crawl_all() -> List[Dict]:
    """Crawl all configured smart sites, with per-site error isolation."""
    all_listings = []

    for site in SMART_CRAWL_SITES:
        try:
            listings = await smart_crawl_site(site)
            all_listings.extend(listings)
        except Exception as e:
            logger.error("SmartCrawl: Site '%s' crashed: %s",
                        site.get('key', '?'), str(e)[:200])

    logger.info("SmartCrawl: Total %d listings from %d sites",
               len(all_listings), len(SMART_CRAWL_SITES))
    return all_listings


async def smart_crawl_url(url: str, custom_task: str = None, deep: bool = True) -> List[Dict]:
    """Crawl an arbitrary URL using the AI agent.
    Called by /smartsearch Telegram command.
    """
    domain = urlparse(url).netloc.replace('www.', '').replace('.', '_')
    site_key = f"custom_{domain}"

    task = custom_task or (
        "Find all apartment/housing listings on this page. "
        "For each listing, extract: title, address, number of rooms, "
        "size in square meters, monthly rent price, and the link/URL. "
        "If there are filter dropdowns or search forms, try to filter for "
        "Berlin apartments under 500 euros. "
        "Return the results as a JSON array."
    )

    site_config = {
        'key': site_key,
        'url': url,
        'task': task,
        'deep_crawl': deep,
    }

    return await smart_crawl_site(site_config)


def run_smart_crawl_sync() -> List[Dict]:
    """Synchronous wrapper for smart_crawl_all()."""
    try:
        return asyncio.run(smart_crawl_all())
    except RuntimeError:
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(smart_crawl_all())
        except ImportError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(lambda: asyncio.run(smart_crawl_all()))
                return future.result(timeout=300)
    except Exception as e:
        logger.error("SmartCrawl sync error: %s", str(e)[:200])
        return []


if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        url = sys.argv[1]
        print(f"Smart crawling: {url}")
        results = asyncio.run(smart_crawl_url(url))
    else:
        print("Smart crawling all configured sites...")
        results = asyncio.run(smart_crawl_all())

    print(f"\n{'='*60}")
    print(f"Found {len(results)} listings:")
    for r in results:
        print(f"  - {r.get('title', '?')} | {r.get('price', '?')} | {r.get('url', '?')[:60]}")
    print(f"{'='*60}")
    print(f"\nLearning Memory: {memory.get_stats()}")
