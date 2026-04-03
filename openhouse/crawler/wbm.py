"""Expose crawler for WBM (Wohnungsbaugesellschaft Berlin-Mitte)"""
import re
import hashlib
from bs4 import BeautifulSoup, Tag
from openhouse.logging import logger
from openhouse.abstract_crawler import Crawler


class WBM(Crawler):
    """Implementation of Crawler interface for WBM"""

    URL_PATTERN = re.compile(r'https://www\.wbm\.de')

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def extract_data(self, raw_data: BeautifulSoup):
        """Extracts all exposes from WBM listing page"""
        entries = []
        listings = raw_data.find_all("div", class_=re.compile(r'openimmo|immo-element|listing|result|angebot'))
        if not listings:
            listings = raw_data.find_all("article")
        if not listings:
            listings = raw_data.find_all("a", href=re.compile(r'/wohnungen.*angebot|/expose'))

        seen_urls = set()
        for listing in listings:
            if not isinstance(listing, Tag):
                continue
            link = listing.find("a", href=True) if listing.name != 'a' else listing
            if not link:
                continue
            url = link.get('href', '')
            if not url or url in seen_urls:
                continue
            if not url.startswith('http'):
                url = 'https://www.wbm.de' + url
            seen_urls.add(url)

            text = listing.get_text(separator=' ', strip=True)
            title = ''
            title_el = listing.find(re.compile(r'h[2-5]'))
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                title = 'WBM Listing'

            rooms = ''
            rooms_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*(?:Zimmer|Zi)', text)
            if rooms_match:
                rooms = rooms_match.group(1)

            size = ''
            size_match = re.search(r'([\d,\.]+)\s*m²', text)
            if size_match:
                size = size_match.group(1) + ' m²'

            price = ''
            price_match = re.search(r'([\d,\.]+)\s*€', text)
            if price_match:
                price = price_match.group(1) + ' €'

            address = ''
            addr_el = listing.find(class_=re.compile(r'address|location|street'))
            if addr_el:
                address = addr_el.get_text(strip=True)

            image = None
            img_tag = listing.find('img')
            if img_tag:
                image = img_tag.get('src') or img_tag.get('data-src', '')
                if image and not image.startswith('http'):
                    image = 'https://www.wbm.de' + image

            ad_id = url.rstrip('/').split('/')[-1]
            processed_id = int(hashlib.sha256(ad_id.encode('utf-8')).hexdigest(), 16) % 10**16

            entries.append({
                'id': processed_id, 'image': image, 'url': url,
                'title': title, 'rooms': rooms, 'price': price,
                'size': size, 'address': address, 'crawler': self.get_name()
            })

        logger.debug('WBM: Number of entries found: %d', len(entries))
        return entries
