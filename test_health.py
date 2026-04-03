#!/usr/bin/env python
"""Health check: test each crawler individually and report status."""
import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.WARNING)

from openhouse.config import Config
from openhouse.idmaintainer import IdMaintainer

config = Config("config.yaml")
config.init_searchers()

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_ids.db")
id_watch = IdMaintainer(db_path)

urls = config.target_urls()
searchers = config.searchers()

print("=" * 70)
print("OpenHouse HEALTH CHECK")
print("=" * 70)
print(f"Python: {sys.version}")
print(f"Config URLs: {len(urls)}")
print(f"Searchers: {len(searchers)}")
print("=" * 70)

results = {}

for url in urls:
    # Find the right searcher for this URL
    searcher = None
    for s in searchers:
        if hasattr(s, 'URL_PATTERN'):
            import re
            if re.search(s.URL_PATTERN, url):
                searcher = s
                break

    name = type(searcher).__name__ if searcher else "Unknown"
    short_url = url[:60] + "..." if len(url) > 60 else url
    print(f"\n--- {name} ---")
    print(f"URL: {short_url}")

    if not searcher:
        print("  SKIP: No matching searcher found")
        results[name] = ("SKIP", 0)
        continue

    start = time.time()
    try:
        exposes = searcher.get_results(url)
        elapsed = time.time() - start
        count = len(exposes)
        print(f"  OK: {count} listings in {elapsed:.1f}s")
        if count > 0:
            first = exposes[0]
            title = first.get("title", "N/A")
            if isinstance(title, str) and len(title) > 50:
                title = title[:50] + "..."
            print(f"  Sample: {title}")
        results[name] = ("OK", count)
    except Exception as e:
        elapsed = time.time() - start
        err_msg = str(e)
        if len(err_msg) > 100:
            err_msg = err_msg[:100] + "..."
        print(f"  FAIL ({elapsed:.1f}s): {err_msg}")
        results[name] = ("FAIL", err_msg)

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
ok_count = sum(1 for v in results.values() if v[0] == "OK")
fail_count = sum(1 for v in results.values() if v[0] == "FAIL")
skip_count = sum(1 for v in results.values() if v[0] == "SKIP")

for name, (status, detail) in results.items():
    icon = {"OK": "OK", "FAIL": "FAIL", "SKIP": "SKIP"}.get(status, "?")
    if status == "OK":
        print(f"  [{icon}] {name}: {detail} listings")
    else:
        print(f"  [{icon}] {name}: {detail}")

print(f"\nTotal: {ok_count} OK, {fail_count} FAIL, {skip_count} SKIP out of {len(results)}")
print("=" * 70)
