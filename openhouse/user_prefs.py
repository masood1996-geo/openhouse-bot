"""User preferences manager for the apartment finder bot"""
import json
import os
from openhouse.logging import logger

DEFAULT_PREFS = {
    "min_price": None,
    "max_price": 1500,
    "min_rooms": 1,
    "max_rooms": None,
    "min_size": 30,
    "max_size": None,
    "preferred_districts": [],
    "excluded_titles": ["Tauschwohnung", "Wohnungstausch", "Tausch", "Swap", "Mietrabatt", "Nachmieter", "Studenten"],
    "notifications_active": True,
    "wbs_required": False,
}


class UserPrefs:
    """Manages user search preferences stored in a JSON file"""

    def __init__(self, prefs_file="user_prefs.json"):
        self.prefs_file = prefs_file
        self.prefs = self._load()

    def _load(self):
        """Load preferences from file, or create defaults"""
        if os.path.exists(self.prefs_file):
            try:
                with open(self.prefs_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    # Merge with defaults for any missing keys
                    merged = {**DEFAULT_PREFS, **saved}
                    return merged
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Error loading prefs: %s. Using defaults.", e)
        return dict(DEFAULT_PREFS)

    def save(self):
        """Save current preferences to file"""
        try:
            with open(self.prefs_file, 'w', encoding='utf-8') as f:
                json.dump(self.prefs, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error("Error saving prefs: %s", e)

    def get(self, key, default=None):
        """Get a preference value"""
        return self.prefs.get(key, default)

    def set(self, key, value):
        """Set a preference value and save"""
        if key in DEFAULT_PREFS or key in self.prefs:
            self.prefs[key] = value
            self.save()
            return True
        return False

    def update(self, updates: dict):
        """Update multiple preferences at once"""
        for key, value in updates.items():
            if key in DEFAULT_PREFS or key in self.prefs:
                self.prefs[key] = value
        self.save()

    def get_summary(self) -> str:
        """Return a human-readable summary of current preferences"""
        p = self.prefs
        lines = ["📋 **Your current search preferences:**\n"]

        if p.get('min_price') or p.get('max_price'):
            price_parts = []
            if p.get('min_price'):
                price_parts.append(f"min €{p['min_price']}")
            if p.get('max_price'):
                price_parts.append(f"max €{p['max_price']}")
            lines.append(f"💰 Price: {', '.join(price_parts)}")

        if p.get('min_rooms') or p.get('max_rooms'):
            room_parts = []
            if p.get('min_rooms'):
                room_parts.append(f"min {p['min_rooms']}")
            if p.get('max_rooms'):
                room_parts.append(f"max {p['max_rooms']}")
            lines.append(f"🏠 Rooms: {', '.join(room_parts)}")

        if p.get('min_size') or p.get('max_size'):
            size_parts = []
            if p.get('min_size'):
                size_parts.append(f"min {p['min_size']}m²")
            if p.get('max_size'):
                size_parts.append(f"max {p['max_size']}m²")
            lines.append(f"📐 Size: {', '.join(size_parts)}")

        if p.get('preferred_districts'):
            lines.append(f"📍 Districts: {', '.join(p['preferred_districts'])}")

        if p.get('wbs_required'):
            lines.append("📄 WBS: Required")

        status = "🟢 Active" if p.get('notifications_active', True) else "🔴 Paused"
        lines.append(f"🔔 Notifications: {status}")

        return '\n'.join(lines)

    def to_filter_dict(self) -> dict:
        """Convert preferences to a dict compatible with OpenHouse's filter config"""
        p = self.prefs
        filters = {}
        if p.get('min_price') is not None:
            filters['min_price'] = p['min_price']
        if p.get('max_price') is not None:
            filters['max_price'] = p['max_price']
        if p.get('min_rooms') is not None:
            filters['min_rooms'] = p['min_rooms']
        if p.get('max_rooms') is not None:
            filters['max_rooms'] = p['max_rooms']
        if p.get('min_size') is not None:
            filters['min_size'] = p['min_size']
        if p.get('max_size') is not None:
            filters['max_size'] = p['max_size']
        if p.get('excluded_titles'):
            filters['excluded_titles'] = p['excluded_titles']
        return filters
