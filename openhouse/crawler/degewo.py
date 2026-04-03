"""Expose crawler for Degewo"""
import re
import hashlib
from bs4 import BeautifulSoup, Tag
from openhouse.logging import logger
from openhouse.abstract_crawler import Crawler


class Degewo(Crawler):
    """Implementation of Crawler interface for Degewo"""

    URL_PATTERN = re.compile(r'https://immosuche\.degewo\.de')

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def extract_data(self, raw_data: BeautifulSoup):
        """Extracts all exposes from a provided Soup object"""
        entries = []
        # Degewo listing cards are anchor tags linking to /immosuche/details/
        listings = raw_data.find_all("a", href=re.compile(r'/immosuche/details/'))
        seen_urls = set()
        for listing in listings:
            if not isinstance(listing, Tag):
                continue
            url = listing.get('href', '')
            if not url or url in seen_urls:
                continue
            if not url.startswith('http'):
                url = 'https://immosuche.degewo.de' + url
            seen_urls.add(url)

            # Extract title
            title = ''
            title_parts = listing.get_text(separator='|', strip=True).split('|')
            # Look for address and description
            address = ''
            for part in title_parts:
                part = part.strip()
                if 'Zimmer' in part or 'm²' in part or '€' in part or part in ('MerkenGemerkt', 'Balkon/Loggia', 'Aufzug', 'barrierefrei', ''):
                    continue
                if not title and ('straße' in part.lower() or 'weg' in part.lower() or 'platz' in part.lower() or 'ring' in part.lower() or '|' in part or any(c.isdigit() for c in part)):
                    address = part
                elif not title:
                    title = part
                elif not address:
                    address = part

            if not title:
                title = address or 'Degewo Listing'

            # Extract rooms
            rooms = ''
            rooms_match = re.search(r'(\d+)\s*Zimmer', listing.get_text())
            if rooms_match:
                rooms = rooms_match.group(1)

            # Extract size
            size = ''
            size_match = re.search(r'([\d,\.]+)\s*m²', listing.get_text())
            if size_match:
                size = size_match.group(1) + ' m²'

            # Extract price (Warmmiete)
            price = ''
            price_match = re.search(r'(?:Warmmiete|Kaltmiete)[:\s]*([\d,\.]+)\s*€', listing.get_text())
            if price_match:
                price = price_match.group(1) + ' €'
            else:
                price_match = re.search(r'([\d,\.]+)\s*€', listing.get_text())
                if price_match:
                    price = price_match.group(1) + ' €'

            # Extract image
            image = None
            img_tag = listing.find('img')
            if img_tag:
                image = img_tag.get('src', '')
                if image and not image.startswith('http'):
                    image = 'https://immosuche.degewo.de' + image

            ad_id = url.split('/')[-1]
            processed_id = int(
                hashlib.sha256(ad_id.encode('utf-8')).hexdigest(), 16
            ) % 10**16

            details = {
                'id': processed_id,
                'image': image,
                'url': url,
                'title': title.strip(),
                'rooms': rooms,
                'price': price,
                'size': size,
                'address': address.strip(),
                'crawler': self.get_name()
            }
            entries.append(details)

        logger.debug('Degewo: Number of entries found: %d', len(entries))
        return entries
