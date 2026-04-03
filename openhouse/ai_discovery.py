import json
import logging
import requests

logger = logging.getLogger(__name__)

# Known apartment portals per country/region — used as seed + deduplication
KNOWN_PORTALS = {
    "de": ["immobilienscout24.de", "immowelt.de", "kleinanzeigen.de", "wg-gesucht.de", "immonet.de"],
    "nl": ["pararius.com", "funda.nl", "kamernet.nl", "huurwoningen.nl"],
    "uk": ["rightmove.co.uk", "zoopla.co.uk", "spareroom.co.uk", "openrent.co.uk"],
    "fr": ["seloger.com", "leboncoin.fr", "pap.fr", "logic-immo.com"],
    "es": ["idealista.com", "fotocasa.es", "habitaclia.com", "pisos.com"],
    "it": ["immobiliare.it", "idealista.it", "subito.it", "casa.it"],
    "at": ["willhaben.at", "immoscout24.at", "immonet.at"],
    "ch": ["homegate.ch", "immoscout24.ch", "comparis.ch"],
    "us": ["zillow.com", "apartments.com", "trulia.com", "craigslist.org"],
    "au": ["realestate.com.au", "domain.com.au", "flatmates.com.au"],
}

CITY_COUNTRY = {
    # Germany
    "berlin": "de", "munich": "de", "münchen": "de", "hamburg": "de",
    "frankfurt": "de", "cologne": "de", "köln": "de", "stuttgart": "de",
    "düsseldorf": "de", "dortmund": "de", "essen": "de", "leipzig": "de",
    # Netherlands
    "amsterdam": "nl", "rotterdam": "nl", "utrecht": "nl", "the hague": "nl",
    "den haag": "nl", "eindhoven": "nl",
    # UK
    "london": "uk", "manchester": "uk", "birmingham": "uk", "leeds": "uk",
    "bristol": "uk", "edinburgh": "uk", "glasgow": "uk",
    # France
    "paris": "fr", "lyon": "fr", "marseille": "fr", "toulouse": "fr",
    # Spain
    "madrid": "es", "barcelona": "es", "valencia": "es", "seville": "es",
    # Italy
    "rome": "it", "milan": "it", "florence": "it", "naples": "it",
    # Austria
    "vienna": "at", "wien": "at", "graz": "at", "salzburg": "at",
    # Switzerland
    "zurich": "ch", "zürich": "ch", "geneva": "ch", "bern": "ch",
    # USA
    "new york": "us", "los angeles": "us", "chicago": "us", "houston": "us",
    "san francisco": "us", "seattle": "us", "boston": "us",
    # Australia
    "sydney": "au", "melbourne": "au", "brisbane": "au", "perth": "au",
}


def discover_providers(config):
    """
    Primary:  DuckDuckGo search (no API key needed)
    Fallback: AI provider call
    Final:    Built-in city-aware portal list
    """
    city    = config.get("city", "Berlin")
    provider = config.get("ai_provider", "openrouter").lower()
    api_key  = config.get("ai_api_key", "")
    model    = config.get("ai_model", "")

    print(f"[*] Discovering apartment portals for {city}...")

    # 1. DuckDuckGo — no API key needed
    urls = _ddg_discover_smart(city)
    if urls:
        print(f"[OK] Instantiated {len(urls)} real estate search paths for {city}.")
        _ddg_agents(config, urls)
        return urls

    # 2. AI fallback (if API key is set)
    if api_key:
        print(f"[*] Asking {provider} AI for portals...")
        base_urls = _ai_discover(city, provider, api_key, model)
        urls = _build_search_urls(city, base_urls)
        if urls:
            print(f"[OK] Configured {len(urls)} portals.")
            _ddg_agents(config, urls)
            return urls

    # 3. Built-in city-aware list
    urls = _builtin_fallback(city)
    print(f"[!] Using built-in portal list for {city}.")
    _ddg_agents(config, urls)
    return urls

def _build_search_urls(city, domains):
    urls = []
    city_lower = city.lower().replace(" ", "-")
    for d in domains:
        if "immobilienscout24.de" in d:
            urls.append(f"https://www.immobilienscout24.de/Suche/de/{city_lower}/{city_lower}/wohnung-mieten?sorting=2")
        elif "immowelt.de" in d:
            urls.append(f"https://www.immowelt.de/liste/{city_lower}/wohnungen/mieten")
        elif "kleinanzeigen.de" in d:
            urls.append(f"https://www.kleinanzeigen.de/s-{city_lower}/wohnung-mieten/c203")
        elif "meinestadt.de" in d:
            urls.append(f"https://www.meinestadt.de/{city_lower}/immobilien/wohnungen")
        elif "11880.com" in d:
            pass # Skip, directory
        else:
            urls.append(d) if d.startswith("http") else urls.append(f"https://{d}")
            
    if "berlin" in city_lower:
        berlin_social_housing = [
            "https://www.gewobag.de",
            "https://www.howoge.de",
            "https://www.wbm.de",
            "https://www.stadtundland.de",
            "https://www.gesobau.de",
            "https://www.degewo.de/wohnungssuche"
        ]
        urls.extend(berlin_social_housing)
        
    # Remove duplicates
    return list(dict.fromkeys(urls))

def _ddg_discover_smart(city):
    domains = _ddg_discover(city)
    return _build_search_urls(city, domains)

def _ddg_agents(config, urls):
    """If requested, search for real estate agents via DDG and display structured info."""
    if not config.get("search_agents"):
        return
    city = config.get("city", "Berlin")
    print(f"[*] Discovering rental agents in {city}...")
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        
        query = f"real estate rental agent agency broker contact in {city}"
        raw_agents = []
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=10)
            for r in results:
                title = r.get("title", "")
                url = r.get("href", "")
                body = r.get("body", "")
                raw_agents.append({"title": title, "url": url, "body": body})
        
        if not raw_agents:
            print("[!] No agents found via search.")
            return

        # Use LLM to extract structured contact info
        api_key = config.get("ai_api_key", "")
        model = config.get("ai_model", "")
        provider = config.get("ai_provider", "")
        
        if api_key and model:
            agents_text = "\n".join([
                f"- {a['title']}: {a['body']} ({a['url']})" for a in raw_agents
            ])
            
            prompt = f"""Extract rental agent/broker contact information from these search results for {city}.
For each agent, output a JSON array of objects with these keys:
- name: string (company/person name)
- phone: string (phone number if found, else "Not listed")
- email: string (email if found, else "Not listed") 
- website: string (website URL)
- hours: string (working hours if found, else "Not listed")
- specialty: string (brief description of what they do)

Return ONLY the raw JSON array. No markdown formatting.

Search results:
{agents_text}"""

            try:
                import openai
                base_url = None
                if provider == "openrouter":
                    base_url = "https://openrouter.ai/api/v1"
                    
                client = openai.OpenAI(base_url=base_url, api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                
                import json
                result_text = str(response.choices[0].message.content).strip()
                # Clean markdown formatting
                for prefix in ["```json", "```"]:
                    if result_text.startswith(prefix):
                        result_text = result_text[len(prefix):]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
                
                agents = json.loads(result_text.strip())
                
                # Print structured blocks to terminal
                print(f"\n{'═'*60}")
                print(f"  🏢  RENTAL AGENTS & BROKERS IN {city.upper()}")
                print(f"{'═'*60}")
                
                telegram_msg_parts = [f"🏢 Rental Agents in {city}\n"]
                
                for i, agent in enumerate(agents[:8], 1):
                    name = agent.get("name", "Unknown")
                    phone = agent.get("phone", "Not listed")
                    email = agent.get("email", "Not listed")
                    website = agent.get("website", "")
                    hours = agent.get("hours", "Not listed")
                    specialty = agent.get("specialty", "")
                    
                    print(f"\n  [{i}] {name}")
                    print(f"      📞 Phone:    {phone}")
                    print(f"      📧 Email:    {email}")
                    print(f"      🌐 Website:  {website}")
                    print(f"      🕐 Hours:    {hours}")
                    print(f"      📋 Type:     {specialty}")
                    print(f"      {'─'*50}")
                    
                    telegram_msg_parts.append(
                        f"\n[{i}] {name}\n"
                        f"📞 {phone}\n"
                        f"📧 {email}\n"
                        f"🌐 {website}\n"
                        f"🕐 {hours}\n"
                        f"📋 {specialty}"
                    )
                
                print(f"{'═'*60}\n")
                
                # Send to Telegram if configured
                telegram_token = config.get("telegram_bot_token", "")
                chat_id = config.get("telegram_chat_id", "")
                if telegram_token and chat_id:
                    telegram_msg = "\n".join(telegram_msg_parts)
                    try:
                        import requests as req
                        req.post(
                            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
                            data={"chat_id": chat_id, "text": telegram_msg},
                            timeout=15
                        )
                        print("[OK] Agent info sent to Telegram.")
                    except Exception as e:
                        logger.warning(f"Failed to send agent info to Telegram: {e}")
                        
                return  # Done — do NOT add any agent URLs to the crawl list
                
            except Exception as e:
                logger.warning(f"LLM agent extraction failed: {e}")
        
        # Fallback: print raw DDG results if LLM not available
        print(f"\n{'═'*60}")
        print(f"  🏢  RENTAL AGENTS IN {city.upper()} (Raw Results)")
        print(f"{'═'*60}")
        for i, a in enumerate(raw_agents[:8], 1):
            print(f"  [{i}] {a['title']}")
            print(f"      🌐 {a['url']}")
            print(f"      📋 {a['body'][:80]}...")
            print(f"      {'─'*50}")
        print(f"{'═'*60}\n")
        
    except Exception as e:
        logger.warning(f"Agent discovery failed: {e}")



def _ddg_discover(city):
    """Search DuckDuckGo for apartment listing portals in the city."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        queries = [
            f"apartments for rent in {city} site listing portal",
            f"wohnung mieten {city}" if _city_country(city) == "de" else f"rent apartment {city}",
        ]

        found_domains = set()
        urls = []
        known = set()
        for domains in KNOWN_PORTALS.values():
            known.update(domains)

        with DDGS() as ddgs:
            for query in queries:
                results = ddgs.text(query, max_results=15)
                for r in results:
                    url = r.get("href", "")
                    domain = _domain(url)
                    # Only include known real estate portals
                    if any(k in domain for k in known) and domain not in found_domains:
                        found_domains.add(domain)
                        urls.append(url)
                    if len(urls) >= 6:
                        break
                if len(urls) >= 6:
                    break

        # If DDG didn't find known portals, supplement with country defaults
        if len(urls) < 3:
            country = _city_country(city)
            if country:
                for portal in KNOWN_PORTALS.get(country, []):
                    if portal not in found_domains and len(urls) < 6:
                        urls.append(f"https://www.{portal}/")
                        found_domains.add(portal)

        return urls

    except ImportError:
        logger.warning("duckduckgo_search not installed. Skipping DDG discovery.")
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return []


def _ai_discover(city, provider, api_key, model):
    """Call the configured AI provider to discover portals."""
    system_prompt = (
        "You are an apartment hunting assistant. "
        "Output ONLY a valid JSON array of 5 apartment listing URLs for the given city. "
        "No markdown, no explanation, just the raw JSON array."
    )
    user_prompt = f"Top 5 apartment rental websites for {city}?"

    endpoints = {
        "openrouter": ("https://openrouter.ai/api/v1/chat/completions",  model or "google/gemini-2.5-flash"),
        "openai":     ("https://api.openai.com/v1/chat/completions",      model or "gpt-4o-mini"),
        "kilo":       ("https://api.kilo.ai/api/gateway/chat/completions", model or "claude-sonnet-4-5"),
        "anthropic":  (None, None),  # Different schema, skip
    }

    endpoint, mdl = endpoints.get(provider, (None, None))
    if not endpoint:
        return []

    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        r = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        content = content.strip("`").lstrip("json").strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"AI discovery failed: {e}")
        return []


def _builtin_fallback(city):
    country = _city_country(city)
    portals = KNOWN_PORTALS.get(country, KNOWN_PORTALS["de"])
    return [f"https://www.{p}/" for p in portals]


def _city_country(city):
    return CITY_COUNTRY.get(city.lower().strip())


def _domain(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url
