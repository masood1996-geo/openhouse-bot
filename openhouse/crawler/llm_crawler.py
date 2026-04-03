"""Universal LLM-Powered Crawler for unknown websites"""
import json
import re
import hashlib
from bs4 import BeautifulSoup
import openai

from openhouse.abstract_crawler import Crawler
from openhouse.logging import logger

class LlmUniversalCrawler(Crawler):
    """Fallback agent taking unknown URLs and parsing DOM using an LLM API"""
    
    # Matches absolutely everything - relies on being evaluated LAST in the pipeline
    URL_PATTERN = re.compile(r'.*')

    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.ai_api_key()
        self.model = config.ai_model()
        self.provider = config.ai_provider()
        
        # Determine the correct base URL for openai library
        base_url = None
        if self.provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
            
        try:
            self.client = openai.OpenAI(
                base_url=base_url,
                api_key=self.api_key
            )
            self.llm_ready = True
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
            self.llm_ready = False

    def is_compatible(self, url: str) -> bool:
        if not self.llm_ready or not self.api_key:
            return False
            
        # Isolate responsibility: If any other native crawler natively supports this URL,
        # we refuse to execute to save tokens.
        for searcher in self.config.searchers():
            if searcher != self and hasattr(searcher, 'URL_PATTERN') and re.search(searcher.URL_PATTERN, url):
                return False
                
        # If no one claimed the URL natively, LLM Agent takes over!
        return True

    def crawl(self, url, max_pages=None):
        """Override crawl() because the parent uses re.search(URL_PATTERN) which matches
        everything with '.*'. We need to use is_compatible() to check if we should
        actually handle this URL."""
        if not self.is_compatible(url):
            return []
        try:
            return self.get_results(url, max_pages)
        except Exception as e:
            logger.warning(f"LLM Crawler failed on {url}: {e}")
            return []
        
    def get_results(self, search_url, max_pages=None, driver=None):
        logger.info(f"LLM Crawler booting headless sequence for: {search_url}")
        
        # Override to enforce Selenium for Javascript rendering and anti-bot bypassing.
        from openhouse.chrome_wrapper import get_chrome_driver
        _driver = None
        try:
            _driver = get_chrome_driver(driver_arguments=None)
            raw_data = self.get_soup_from_url(search_url, driver=_driver)
            return self.extract_data(raw_data)
        except Exception as e:
            logger.warning(f"LLM Crawler headless engine failed: {e}")
            return []
        finally:
            if _driver:
                _driver.quit()

    def extract_data(self, raw_data: BeautifulSoup):
        # We need to strip large useless elements like script, style, meta
        # This keeps the LLM context window low to save money.
        for element in raw_data(['script', 'style', 'nav', 'footer', 'header', 'meta', 'svg', 'iframe']):
            element.decompose()
        
        text = raw_data.get_text(separator=' ', strip=True)
        # Soft truncate text length to prevent breaking context window
        text = text[:15000]

        prompt = f"""
You are an expert data extraction agent. I will provide you with the raw text from an apartment rental website.
Your job is to find all the apartment rental listings on this page and extract them strictly into JSON format.

Output a valid JSON array of objects, with each object having the exact following keys:
- title: string
- rooms: string (e.g. "2")
- size: string (e.g. "50 m²")
- price: string (e.g. "800 €")
- address: string
- url: string (absolute URL of the detailed listing)
- image: string (absolute URL to the primary image if available)

Return ONLY the raw JSON array. Start your response with '[' and end with ']'. Do not include markdown formatting like ```json.

Website text:
{text}
"""
        
        try:
            logger.info(f"Sending unidentified website DOM to {self.model} for structural digestion...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            ) # type: ignore
            
            result_text = str(response.choices[0].message.content).strip()
            
            # Clean up potential markdown formatting silently added by generic models
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
                
            entries = json.loads(result_text)
            
            # Ensure proper schema before pushing output to pipeline
            valid_entries = []
            for e in entries:
                ad_id = e.get("url", e.get("title", ""))
                processed_id = int(hashlib.sha256(ad_id.encode('utf-8')).hexdigest(), 16) % 10**16

                valid_entries.append({
                    "id": processed_id,
                    "title": e.get("title", ""),
                    "rooms": str(e.get("rooms", "")),
                    "size": str(e.get("size", "")),
                    "price": str(e.get("price", "")),
                    "address": e.get("address", ""),
                    "url": e.get("url", ""),
                    "image": e.get("image", None),
                    "crawler": "LLM_Crawler"
                })
            
            logger.info(f"LLM Crawler discovered {len(valid_entries)} listings!")
            return valid_entries
            
        except json.JSONDecodeError:
            logger.warning("LLM Crawler failed to decode JSON output. Skipping URL.")
            return []
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return []
