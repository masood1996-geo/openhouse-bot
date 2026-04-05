"""Default OpenHouse implementation for the command line"""
import time
import traceback
from itertools import chain
import requests

from openhouse.logging import logger
from openhouse.config import YamlConfig
from openhouse.filter import Filter
from openhouse.processor import ProcessorChain
from openhouse.captcha.captcha_solver import CaptchaUnsolvableError
from openhouse.exceptions import ConfigException
from openhouse.bot_events import (
    EventBus, BotEvent, BotEventName, BotEventStatus, FailureClass,
)

class Hunter:
    """Basic methods for crawling and processing / filtering exposes"""

    def __init__(self, config: YamlConfig, id_watch, event_bus: EventBus = None):
        self.config = config
        if not isinstance(self.config, YamlConfig):
            raise ConfigException(
                "Invalid config for hunter - should be a 'Config' object")
        self.id_watch = id_watch
        self.events = event_bus or EventBus()

    def crawl_for_exposes(self, max_pages=None):
        """Trigger a new crawl of the configured URLs"""
        urls = self.config.target_urls()
        self.events.emit_event(BotEvent.crawl_started(urls))

        def try_crawl(searcher, url, max_pages):
            self.events.emit(
                BotEventName.CRAWL_URL_FETCHING,
                detail=f"Fetching: {url}",
                data={"url": url},
            )
            try:
                results = searcher.crawl(url, max_pages)
                self.events.emit(
                    BotEventName.CRAWL_URL_COMPLETED,
                    status=BotEventStatus.COMPLETED,
                    detail=f"Fetched: {url}",
                    data={"url": url},
                )
                return results
            except CaptchaUnsolvableError:
                self.events.emit(
                    BotEventName.CRAWL_CAPTCHA_FAILED,
                    status=BotEventStatus.FAILED,
                    detail=f"Captcha unsolvable on {url}",
                    data={"url": url},
                    failure_class=FailureClass.CAPTCHA,
                )
                logger.info("Error while scraping url %s: the captcha was unsolvable", url)
                return []
            except requests.exceptions.RequestException:
                self.events.emit(
                    BotEventName.CRAWL_URL_FAILED,
                    status=BotEventStatus.FAILED,
                    detail=f"Request failed: {url}",
                    data={"url": url, "traceback": traceback.format_exc()[-200:]},
                    failure_class=FailureClass.NETWORK,
                )
                logger.info("Error while scraping url %s:\n%s", url, traceback.format_exc())
                return []

        return chain(*[try_crawl(searcher, url, max_pages)
                       for searcher in self.config.searchers()
                       for url in urls])

    def hunt_flats(self, max_pages: None|int = None):
        """Crawl, process and filter exposes"""
        start_time = time.time()

        filter_set = Filter.builder() \
                           .read_config(self.config) \
                           .filter_already_seen(self.id_watch) \
                           .build()

        processor_chain = ProcessorChain.builder(self.config) \
                                        .save_all_exposes(self.id_watch) \
                                        .apply_filter(filter_set) \
                                        .resolve_addresses() \
                                        .calculate_durations() \
                                        .send_messages() \
                                        .build()

        result = []
        total_found = 0
        # We need to iterate over this list to force the evaluation of the pipeline
        for expose in processor_chain.process(self.crawl_for_exposes(max_pages)):
            total_found += 1
            logger.info('New offer: %s', expose['title'])
            self.events.emit_event(BotEvent.listing_found(expose))
            result.append(expose)

        duration = time.time() - start_time
        self.events.emit_event(
            BotEvent.crawl_completed(
                found=total_found,
                new=len(result),
                filtered=total_found - len(result),
                duration=duration,
            )
        )

        return result

