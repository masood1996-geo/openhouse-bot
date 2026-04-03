import os
import sys
import logging
logging.basicConfig(level=logging.DEBUG)
sys.path.insert(0, r'c:\Users\User\Downloads\Apartment finder\OpenHouse')
from ai_telegram_bot import get_config, run_crawl
print('starting crawl')
results = run_crawl()
print('crawl finished, results:', len(results))
