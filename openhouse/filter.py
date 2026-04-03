"""Module with implementations of standard expose filters"""
from functools import reduce
import re
from abc import ABC, ABCMeta
from typing import List, Any


class AbstractFilter(ABC):
    """Abstract base class for filters"""

    def is_interesting(self, _expose) -> bool:
        """Return True if an expose should be included in the output, False otherwise"""
        return True


class ExposeHelper:
    """Helper functions for extracting data from expose text"""

    @staticmethod
    def get_price(expose):
        """Extracts the price from a price text"""
        price_match = re.search(r'\d+([\.,]\d+)?', expose['price'])
        if price_match is None:
            return None
        return float(price_match[0].replace(".", "").replace(",", "."))

    @staticmethod
    def get_size(expose):
        """Extracts the size from a size text"""
        size_match = re.search(r'\d+([\.,]\d+)?', expose['size'])
        if size_match is None:
            return None
        return float(size_match[0].replace(",", "."))

    @staticmethod
    def get_rooms(expose):
        """Extracts the number of rooms from a room text"""
        rooms_match = re.search(r'\d+([\.,]\d+)?', expose['rooms'])
        if rooms_match is None:
            return None
        return float(rooms_match[0].replace(",", "."))


class AlreadySeenFilter(AbstractFilter):
    """Filter exposes that have already been processed"""

    def __init__(self, id_watch):
        self.id_watch = id_watch

    def is_interesting(self, expose):
        """Returns true if an expose should be kept in the pipeline"""
        if not self.id_watch.is_processed(expose['id']):
            self.id_watch.mark_processed(expose['id'])
            return True
        return False


class MaxPriceFilter(AbstractFilter):
    """Exclude exposes above a given price"""

    def __init__(self, max_price):
        self.max_price = max_price

    def is_interesting(self, expose):
        """True if expose is below the max price"""
        price = ExposeHelper.get_price(expose)
        if price is None:
            return True
        return price <= self.max_price


class MinPriceFilter(AbstractFilter):
    """Exclude exposes below a given price"""

    def __init__(self, min_price):
        self.min_price = min_price

    def is_interesting(self, expose):
        """True if expose is above the min price"""
        price = ExposeHelper.get_price(expose)
        if price is None:
            return True
        return price >= self.min_price


class MaxSizeFilter(AbstractFilter):
    """Exclude exposes above a given size"""

    def __init__(self, max_size):
        self.max_size = max_size

    def is_interesting(self, expose):
        """True if expose is below the max size"""
        size = ExposeHelper.get_size(expose)
        if size is None:
            return True
        return size <= self.max_size


class MinSizeFilter(AbstractFilter):
    """Exclude exposes below a given size"""

    def __init__(self, min_size):
        self.min_size = min_size

    def is_interesting(self, expose):
        """True if expose is above the min size"""
        size = ExposeHelper.get_size(expose)
        if size is None:
            return True
        return size >= self.min_size


class MaxRoomsFilter(AbstractFilter):
    """Exclude exposes above a given number of rooms"""

    def __init__(self, max_rooms):
        self.max_rooms = max_rooms

    def is_interesting(self, expose):
        """True if expose is below the max number of rooms"""
        rooms = ExposeHelper.get_rooms(expose)
        if rooms is None:
            return True
        return rooms <= self.max_rooms


class MinRoomsFilter(AbstractFilter):
    """Exclude exposes below a given number of rooms"""

    def __init__(self, min_rooms):
        self.min_rooms = min_rooms

    def is_interesting(self, expose):
        """True if expose is above the min number of rooms"""
        rooms = ExposeHelper.get_rooms(expose)
        if rooms is None:
            return True
        return rooms >= self.min_rooms


class TitleFilter(AbstractFilter):
    """Exclude exposes whose titles match the provided terms"""

    def __init__(self, filtered_titles):
        self.filtered_titles = filtered_titles

    def is_interesting(self, expose):
        """True unless title matches the filtered titles"""
        combined_excludes = "(" + ")|(".join(self.filtered_titles) + ")"
        found_objects = re.search(
            combined_excludes, expose['title'], re.IGNORECASE)
        # send all non matching regex patterns
        if not found_objects:
            return True
        return False


class ExcludeSwapsFilter(AbstractFilter):
    """Exclude apartment swaps based on title/address containing swap-related keywords"""

    SWAP_PATTERNS = re.compile(
        r'tausch|wohnungstausch|tauschangebot|tauschwohnung|'
        r'wohnung\s*tausch|swap|exchange|'
        r'suche.*biete|biete.*suche|'
        r'ringtausch|gegen\s*tausch|im\s*tausch',
        re.IGNORECASE
    )

    def __init__(self, exclude_swaps_flag: bool):
        self.exclude_swaps_flag = exclude_swaps_flag

    def is_interesting(self, expose):
        if not self.exclude_swaps_flag:
            return True
        title = expose.get('title', '')
        address = expose.get('address', '')
        combined = f"{title} {address}"
        return not bool(self.SWAP_PATTERNS.search(combined))


class CityFilter(AbstractFilter):
    """Reject listings that don't mention the target city in address or URL"""

    def __init__(self, target_city: str):
        self.city_lower = target_city.lower().strip()
        # Build pattern with common German address abbreviations
        city_variants = [self.city_lower]
        if self.city_lower == "munich":
            city_variants.append("münchen")
        elif self.city_lower == "münchen":
            city_variants.append("munich")
        elif self.city_lower == "cologne":
            city_variants.append("köln")
        elif self.city_lower == "köln":
            city_variants.append("cologne")
        self.city_pattern = re.compile(
            '|'.join(re.escape(v) for v in city_variants), re.IGNORECASE
        )

    def is_interesting(self, expose):
        address = expose.get('address', '')
        url = expose.get('url', '')
        title = expose.get('title', '')
        combined = f"{address} {url} {title}"
        # If the listing has address info and doesn't mention our city, reject it
        if address and not self.city_pattern.search(combined):
            return False
        return True


class PPSFilter(AbstractFilter):
    """Exclude exposes above a given price per square"""

    def __init__(self, max_pps):
        self.max_pps = max_pps

    def is_interesting(self, expose):
        """True if price per square is below max price per square"""
        size = ExposeHelper.get_size(expose)
        price = ExposeHelper.get_price(expose)
        if size is None or price is None:
            return True
        pps = price / size
        return pps <= self.max_pps


class QualityGateFilter(AbstractFilter):
    """
    Reject garbage listings: empty titles, navigation items, press releases,
    corporate pages, and other non-apartment content that crawlers accidentally pick up.
    Always active — runs as the first filter in the chain.
    """

    # Patterns that indicate corporate/non-listing content
    GARBAGE_PATTERNS = re.compile(
        r'^(?:Gewobag|WBM|HOWOGE|Gesobau|degewo|Stadt und Land)\s',
        re.IGNORECASE
    )

    NON_LISTING_KEYWORDS = re.compile(
        r'(?:Onlinemagazin|Wohnberechtigungsschein|Grundsteuer|'
        r'SEPA|Lastschrift|Machbarkeitsstudie|Glasfaserausbau|'
        r'Denkmalschutz|Wettbewerb|Siegerentwürfe|Schlüsselübergabe|'
        r'Spielfläche|Zahlungsverkehr|digitales Magazin|Pressemitteilung|'
        r'Mieterbeiratswahl|Ratgeber|Sprechzeiten|Rufnummer|Service-Center|'
        r'Quartier-Strom|Innovation|Digitalisierung|Startups|'
        r'Geschäftsführer|Kredit von|Berufs- und Ausbildung|'
        r'Wir bauen für|Städtisch Grün|offenen Denkmals|'
        r'Sport- und Spielfläche|Neue Regelungen|StarCraft|Podcast)',
        re.IGNORECASE
    )

    def is_interesting(self, expose):
        title = expose.get('title', '').strip()
        url = expose.get('url', '')

        # Reject empty or very short titles (< 5 chars)
        if len(title) < 5:
            return False

        # Reject if title is just a company name
        if self.GARBAGE_PATTERNS.match(title):
            return False

        # Reject corporate/PR content
        if self.NON_LISTING_KEYWORDS.search(title):
            return False

        # Reject if no URL at all
        if not url:
            return False

        return True

class FilterBuilder:
    """Construct a filter chain"""
    filters: List[AbstractFilter]

    def __init__(self):
        self.filters = []

    def _append_filter_if_not_empty(self, filter_class: ABCMeta, filter_config: Any):
        """Appends a filter to the list if its configuration is set"""
        if not filter_config:
            return
        self.filters.append(filter_class(filter_config))

    def read_config(self, config):
        """Adds filters from a config dictionary"""
        self._append_filter_if_not_empty(TitleFilter, config.excluded_titles())
        self._append_filter_if_not_empty(MinPriceFilter, config.min_price())
        self._append_filter_if_not_empty(MaxPriceFilter, config.max_price())
        self._append_filter_if_not_empty(MinSizeFilter, config.min_size())
        self._append_filter_if_not_empty(MaxSizeFilter, config.max_size())
        self._append_filter_if_not_empty(MinRoomsFilter, config.min_rooms())
        self._append_filter_if_not_empty(MaxRoomsFilter, config.max_rooms())
        self._append_filter_if_not_empty(
            PPSFilter, config.max_price_per_square())
        
        if config.exclude_swaps():
            self.filters.append(ExcludeSwapsFilter(True))

        # City filter — reject listings from other cities
        target_city = config.target_city()
        if target_city:
            self.filters.append(CityFilter(target_city))

        # Quality gate — always active, rejects garbage listings
        self.filters.insert(0, QualityGateFilter())
            
        return self

    def filter_already_seen(self, id_watch):
        """Filter exposes that have already been seen"""
        self.filters.append(AlreadySeenFilter(id_watch))
        return self

    def build(self):
        """Return the compiled filter"""
        return Filter(self.filters)


class Filter:
    """Abstract filter object"""

    filters: List[AbstractFilter]

    def __init__(self, filters: List[AbstractFilter]):
        self.filters = filters

    def is_interesting_expose(self, expose):
        """Apply all filters to this expose"""
        return reduce((lambda x, y: x and y),
                      map((lambda x: x.is_interesting(expose)), self.filters), True)

    def filter(self, exposes):
        """Apply all filters to every expose in the list"""
        return filter(self.is_interesting_expose, exposes)

    @staticmethod
    def builder():
        """Return a new filter builder"""
        return FilterBuilder()
