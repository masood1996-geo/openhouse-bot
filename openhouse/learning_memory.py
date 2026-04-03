"""Learning Memory — Strategy caching with scoring for the self-learning web agent.

Stores successful action sequences per site so the agent can replay them
without needing the LLM on subsequent visits (fast path). Falls back to
LLM exploration when saved strategies fail (slow path).

Inspired by reinforcement learning principles:
- Successful strategies get score +1
- Failed strategies get score -1
- Strategies below threshold get deleted
- New strategies discovered by LLM exploration replace old ones
"""
import json
import os
import time
from typing import Dict, List, Optional
from openhouse.logging import logger

DEFAULT_MEMORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "learning_memory.json"
)


class LearningMemory:
    """Persistent per-site strategy memory with scoring."""

    def __init__(self, memory_file: str = DEFAULT_MEMORY_FILE):
        self.memory_file = memory_file
        self.strategies: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load strategies from disk."""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    self.strategies = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load learning memory: %s", e)
                self.strategies = {}

    def _save(self):
        """Persist strategies to disk."""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.strategies, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error("Failed to save learning memory: %s", e)

    def get_strategy(self, site_key: str) -> Optional[dict]:
        """Get the best strategy for a site, if one exists with positive score."""
        strategy = self.strategies.get(site_key)
        if strategy and strategy.get('score', 0) > 0:
            return strategy
        return None

    def save_strategy(self, site_key: str, task_description: str,
                      extraction_prompt: str, results_count: int,
                      css_selectors: Optional[List[str]] = None,
                      navigation_steps: Optional[List[str]] = None):
        """Save a successful strategy for a site."""
        existing = self.strategies.get(site_key, {})
        old_score = existing.get('score', 0)

        self.strategies[site_key] = {
            'site_key': site_key,
            'task_description': task_description,
            'extraction_prompt': extraction_prompt,
            'css_selectors': css_selectors or [],
            'navigation_steps': navigation_steps or [],
            'results_count': results_count,
            'score': old_score + 1,
            'last_success': time.time(),
            'last_updated': time.time(),
            'total_successes': existing.get('total_successes', 0) + 1,
            'total_failures': existing.get('total_failures', 0),
        }
        self._save()
        logger.info("Strategy saved for '%s' (score: %d, results: %d)",
                    site_key, self.strategies[site_key]['score'], results_count)

    def record_failure(self, site_key: str):
        """Record a strategy failure — demotes the score."""
        if site_key in self.strategies:
            self.strategies[site_key]['score'] -= 1
            self.strategies[site_key]['total_failures'] = \
                self.strategies[site_key].get('total_failures', 0) + 1
            self.strategies[site_key]['last_updated'] = time.time()

            # Delete strategies that fall below -3
            if self.strategies[site_key]['score'] < -3:
                logger.warning("Strategy for '%s' too many failures, deleting.", site_key)
                del self.strategies[site_key]
            self._save()
            logger.info("Strategy failure recorded for '%s'", site_key)

    def get_all_sites(self) -> List[str]:
        """Get all tracked site keys."""
        return list(self.strategies.keys())

    def get_stats(self) -> dict:
        """Get summary statistics."""
        total = len(self.strategies)
        positive = sum(1 for s in self.strategies.values() if s.get('score', 0) > 0)
        return {
            'total_strategies': total,
            'positive_strategies': positive,
            'sites': {k: {
                'score': v.get('score', 0),
                'successes': v.get('total_successes', 0),
                'failures': v.get('total_failures', 0),
            } for k, v in self.strategies.items()}
        }

    def generate_replay_prompt(self, site_key: str) -> Optional[str]:
        """Generate a prompt for the LLM to replay a known strategy."""
        strategy = self.get_strategy(site_key)
        if not strategy:
            return None

        steps = strategy.get('navigation_steps', [])
        selectors = strategy.get('css_selectors', [])
        discovered_urls = strategy.get('discovered_urls', [])

        prompt = (
            f"I have visited this site before successfully. "
            f"Here is what worked last time:\n\n"
        )
        if steps:
            prompt += "Navigation steps that worked:\n"
            for i, step in enumerate(steps, 1):
                prompt += f"  {i}. {step}\n"
            prompt += "\n"
        if selectors:
            prompt += f"CSS selectors that contained listings: {', '.join(selectors)}\n\n"
        if discovered_urls:
            prompt += "Previously discovered listing page URLs:\n"
            for u in discovered_urls[:10]:  # Limit to 10 URLs
                prompt += f"  - {u}\n"
            prompt += "\nTry visiting these URLs directly for faster extraction.\n\n"

        prompt += (
            f"Last time I found {strategy.get('results_count', 0)} listings.\n"
            f"Try to follow the same approach first. "
            f"If the page layout has changed, adapt and find a new approach."
        )
        return prompt

    def save_discovered_urls(self, site_key: str, urls: List[str]):
        """Save discovered subpage URLs for a site (for deep crawl 1-shot searching)."""
        if site_key not in self.strategies:
            self.strategies[site_key] = {
                'site_key': site_key,
                'score': 0,
                'total_successes': 0,
                'total_failures': 0,
            }

        existing_urls = set(self.strategies[site_key].get('discovered_urls', []))
        existing_urls.update(urls)
        self.strategies[site_key]['discovered_urls'] = list(existing_urls)[:50]  # Cap at 50
        self.strategies[site_key]['last_updated'] = time.time()
        self._save()
        logger.info("Saved %d discovered URLs for '%s' (total: %d)",
                    len(urls), site_key, len(self.strategies[site_key]['discovered_urls']))

    def get_discovered_urls(self, site_key: str) -> List[str]:
        """Get previously discovered subpage URLs for a site."""
        strategy = self.strategies.get(site_key, {})
        return strategy.get('discovered_urls', [])

