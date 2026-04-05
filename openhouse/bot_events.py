"""
Structured event protocol for OpenHouse Bot.

Adapted from claw-code-parity's lane_events.rs pattern.
Instead of unstructured logger.info() calls scattered throughout the codebase,
this module provides typed, machine-readable events for every significant
bot lifecycle moment.

Architecture:
    BotEventName   → Enum of all possible event types (dot-namespaced)
    BotEventStatus → Current bot/subsystem state
    FailureClass   → Categorized failure reason for root-cause analysis
    BotEvent       → Typed event dataclass with serialization
    EventBus       → Centralized event emission, logging, and history

Usage:
    from openhouse.bot_events import EventBus, BotEventName

    bus = EventBus()
    bus.emit(BotEventName.CRAWL_STARTED, detail="Scanning 5 URLs")
    bus.emit(BotEventName.LISTING_FOUND, data={"title": "2BR Berlin", "price": "800€"})
    bus.emit(BotEventName.CRAWL_COMPLETED, data={"found": 12, "new": 3})

    # Get structured event history
    history = bus.history(limit=50)
    stats = bus.stats()
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Event Names ─────────────────────────────────────────────────────

class BotEventName(Enum):
    """
    Structured event names for every bot lifecycle phase.

    Uses dot-namespaced convention from claw-code-parity's lane_events.
    Events are organized by subsystem:
        bot.*       → Overall bot lifecycle
        crawl.*     → Crawling operations
        listing.*   → Individual listing events
        filter.*    → Filtering pipeline events
        notify.*    → Notification dispatch events
        config.*    → Configuration events
        recovery.*  → Error and recovery events
    """

    # ── Bot Lifecycle ──
    BOT_STARTED = "bot.started"
    BOT_READY = "bot.ready"
    BOT_STOPPED = "bot.stopped"
    BOT_HEARTBEAT = "bot.heartbeat"
    BOT_ERROR = "bot.error"

    # ── Crawl Operations ──
    CRAWL_STARTED = "crawl.started"
    CRAWL_URL_FETCHING = "crawl.url.fetching"
    CRAWL_URL_COMPLETED = "crawl.url.completed"
    CRAWL_URL_FAILED = "crawl.url.failed"
    CRAWL_COMPLETED = "crawl.completed"
    CRAWL_CAPTCHA_DETECTED = "crawl.captcha.detected"
    CRAWL_CAPTCHA_SOLVED = "crawl.captcha.solved"
    CRAWL_CAPTCHA_FAILED = "crawl.captcha.failed"

    # ── Listing Events ──
    LISTING_FOUND = "listing.found"
    LISTING_NEW = "listing.new"
    LISTING_DUPLICATE = "listing.duplicate"
    LISTING_ENRICHED = "listing.enriched"

    # ── Filter Pipeline ──
    FILTER_APPLIED = "filter.applied"
    FILTER_REJECTED = "filter.rejected"
    FILTER_PASSED = "filter.passed"
    FILTER_QUALITY_GATE = "filter.quality_gate"
    FILTER_SWAP_DETECTED = "filter.swap_detected"
    FILTER_CITY_MISMATCH = "filter.city_mismatch"

    # ── Notification Dispatch ──
    NOTIFY_SENDING = "notify.sending"
    NOTIFY_SENT = "notify.sent"
    NOTIFY_FAILED = "notify.failed"
    NOTIFY_RATE_LIMITED = "notify.rate_limited"

    # ── Configuration ──
    CONFIG_LOADED = "config.loaded"
    CONFIG_URLS_DISCOVERED = "config.urls_discovered"
    CONFIG_FILTERS_ACTIVE = "config.filters_active"

    # ── Recovery / Errors ──
    RECOVERY_ATTEMPTED = "recovery.attempted"
    RECOVERY_SUCCEEDED = "recovery.succeeded"
    RECOVERY_ESCALATED = "recovery.escalated"

    # ── Loop / Schedule ──
    LOOP_CYCLE_START = "loop.cycle.start"
    LOOP_CYCLE_END = "loop.cycle.end"
    LOOP_SLEEPING = "loop.sleeping"


# ─── Event Status ────────────────────────────────────────────────────

class BotEventStatus(Enum):
    """
    Current status of the bot/subsystem at event emission time.
    Maps to claw-code-parity's LaneEventStatus.
    """

    RUNNING = "running"
    READY = "ready"
    IDLE = "idle"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


# ─── Failure Classification ─────────────────────────────────────────

class FailureClass(Enum):
    """
    Categorized failure reasons for root-cause analysis.
    Maps to claw-code-parity's LaneFailureClass.
    """

    NETWORK = "network"
    CAPTCHA = "captcha"
    RATE_LIMIT = "rate_limit"
    PARSE_ERROR = "parse_error"
    BROWSER_CRASH = "browser_crash"
    CONFIG_ERROR = "config_error"
    NOTIFICATION_ERROR = "notification_error"
    FILTER_ERROR = "filter_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


# ─── Bot Event ───────────────────────────────────────────────────────

@dataclass
class BotEvent:
    """
    Typed, structured event emitted during bot operation.

    Follows claw-code-parity's LaneEvent pattern:
    - Named event type (dot-namespaced)
    - Current status
    - ISO 8601 timestamp
    - Optional failure classification
    - Optional detail string
    - Optional structured data payload
    """

    event: BotEventName
    status: BotEventStatus
    emitted_at: str = ""
    failure_class: Optional[FailureClass] = None
    detail: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if not self.emitted_at:
            self.emitted_at = datetime.now(timezone.utc).isoformat()

    # ── Builder Pattern (mirroring Rust's with_* chain) ──

    def with_failure(self, failure_class: FailureClass) -> "BotEvent":
        """Attach a failure classification."""
        self.failure_class = failure_class
        return self

    def with_detail(self, detail: str) -> "BotEvent":
        """Attach a human-readable detail string."""
        self.detail = detail
        return self

    def with_data(self, data: Dict[str, Any]) -> "BotEvent":
        """Attach a structured data payload."""
        self.data = data
        return self

    # ── Serialization ──

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a structured dict for logging/telemetry/JSON."""
        result = {
            "event": self.event.value,
            "status": self.status.value,
            "emitted_at": self.emitted_at,
        }
        if self.failure_class is not None:
            result["failure_class"] = self.failure_class.value
        if self.detail is not None:
            result["detail"] = self.detail
        if self.data is not None:
            result["data"] = self.data
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    # ── Factory Methods (mirroring Rust's constructor helpers) ──

    @classmethod
    def started(cls, detail: Optional[str] = None) -> "BotEvent":
        """Create a bot.started event."""
        return cls(
            event=BotEventName.BOT_STARTED,
            status=BotEventStatus.RUNNING,
            detail=detail,
        )

    @classmethod
    def crawl_started(cls, urls: List[str]) -> "BotEvent":
        """Create a crawl.started event."""
        return cls(
            event=BotEventName.CRAWL_STARTED,
            status=BotEventStatus.RUNNING,
            detail=f"Crawling {len(urls)} URLs",
            data={"urls": urls, "url_count": len(urls)},
        )

    @classmethod
    def crawl_completed(
        cls, found: int, new: int, filtered: int, duration: float
    ) -> "BotEvent":
        """Create a crawl.completed event."""
        return cls(
            event=BotEventName.CRAWL_COMPLETED,
            status=BotEventStatus.COMPLETED,
            detail=f"Found {found} listings ({new} new, {filtered} filtered)",
            data={
                "total_found": found,
                "new_listings": new,
                "filtered_out": filtered,
                "duration_seconds": round(duration, 2),
            },
        )

    @classmethod
    def listing_found(cls, expose: Dict[str, Any]) -> "BotEvent":
        """Create a listing.found event from an expose dict."""
        return cls(
            event=BotEventName.LISTING_FOUND,
            status=BotEventStatus.RUNNING,
            detail=expose.get("title", "Unknown listing"),
            data={
                "id": expose.get("id"),
                "title": expose.get("title"),
                "price": expose.get("price"),
                "size": expose.get("size"),
                "rooms": expose.get("rooms"),
                "address": expose.get("address"),
                "url": expose.get("url"),
            },
        )

    @classmethod
    def filter_rejected(
        cls, expose: Dict[str, Any], reason: str
    ) -> "BotEvent":
        """Create a filter.rejected event."""
        return cls(
            event=BotEventName.FILTER_REJECTED,
            status=BotEventStatus.RUNNING,
            detail=f"Rejected: {reason}",
            data={
                "title": expose.get("title"),
                "reason": reason,
            },
        )

    @classmethod
    def notify_sent(cls, channel: str, count: int) -> "BotEvent":
        """Create a notify.sent event."""
        return cls(
            event=BotEventName.NOTIFY_SENT,
            status=BotEventStatus.COMPLETED,
            detail=f"Sent {count} notifications via {channel}",
            data={"channel": channel, "count": count},
        )

    @classmethod
    def failed(
        cls,
        event_name: BotEventName,
        failure: FailureClass,
        detail: str,
    ) -> "BotEvent":
        """Create a typed failure event."""
        return cls(
            event=event_name,
            status=BotEventStatus.FAILED,
            failure_class=failure,
            detail=detail,
        )

    @classmethod
    def recovery(cls, succeeded: bool, detail: str) -> "BotEvent":
        """Create a recovery event."""
        name = (
            BotEventName.RECOVERY_SUCCEEDED
            if succeeded
            else BotEventName.RECOVERY_ESCALATED
        )
        status = (
            BotEventStatus.COMPLETED
            if succeeded
            else BotEventStatus.FAILED
        )
        return cls(event=name, status=status, detail=detail)

    def __repr__(self) -> str:
        status_icon = {
            BotEventStatus.RUNNING: "🔄",
            BotEventStatus.READY: "✅",
            BotEventStatus.IDLE: "💤",
            BotEventStatus.BLOCKED: "🚫",
            BotEventStatus.COMPLETED: "✅",
            BotEventStatus.FAILED: "❌",
            BotEventStatus.RECOVERING: "🔧",
        }.get(self.status, "❓")

        return (
            f"BotEvent({status_icon} {self.event.value} "
            f"| {self.detail or 'no detail'})"
        )


# ─── Event Bus ───────────────────────────────────────────────────────

class EventBus:
    """
    Centralized event emission, logging, and history tracking.

    All subsystems emit events through this bus. It provides:
    - Structured logging (events → logger + structured dicts)
    - In-memory event history with configurable size
    - Subscriber pattern for event-driven reactions
    - Statistics and diagnostics

    Usage:
        bus = EventBus()
        bus.emit(BotEventName.CRAWL_STARTED, detail="5 URLs")
        bus.on(BotEventName.LISTING_NEW, lambda e: send_notification(e))
    """

    def __init__(self, max_history: int = 1000):
        self._history: List[BotEvent] = []
        self._max_history = max_history
        self._subscribers: Dict[BotEventName, List[Callable]] = {}
        self._counters: Dict[str, int] = {}

    def emit(
        self,
        event_name: BotEventName,
        status: BotEventStatus = BotEventStatus.RUNNING,
        detail: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        failure_class: Optional[FailureClass] = None,
    ) -> BotEvent:
        """
        Emit a structured event.

        Creates a BotEvent, logs it, stores in history,
        and notifies subscribers.

        Args:
            event_name: The event type to emit.
            status: Current status of the emitting subsystem.
            detail: Human-readable description.
            data: Structured payload data.
            failure_class: Optional failure classification.

        Returns:
            The emitted BotEvent.
        """
        event = BotEvent(
            event=event_name,
            status=status,
            detail=detail,
            data=data,
            failure_class=failure_class,
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Update counters
        counter_key = event_name.value
        self._counters[counter_key] = self._counters.get(counter_key, 0) + 1

        # Log the event
        log_level = logging.WARNING if status == BotEventStatus.FAILED else logging.INFO
        logger.log(
            log_level,
            "[%s] %s%s",
            event_name.value,
            detail or "",
            f" | failure={failure_class.value}" if failure_class else "",
        )

        # Notify subscribers
        for callback in self._subscribers.get(event_name, []):
            try:
                callback(event)
            except Exception as e:
                logger.warning(
                    "Event subscriber error for %s: %s",
                    event_name.value, e,
                )

        return event

    def emit_event(self, event: BotEvent) -> BotEvent:
        """
        Emit a pre-built BotEvent (from factory methods).

        Args:
            event: A BotEvent instance to emit.

        Returns:
            The emitted BotEvent.
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        counter_key = event.event.value
        self._counters[counter_key] = self._counters.get(counter_key, 0) + 1

        log_level = logging.WARNING if event.status == BotEventStatus.FAILED else logging.INFO
        logger.log(
            log_level,
            "[%s] %s",
            event.event.value,
            event.detail or "",
        )

        for callback in self._subscribers.get(event.event, []):
            try:
                callback(event)
            except Exception as e:
                logger.warning(
                    "Event subscriber error for %s: %s",
                    event.event.value, e,
                )

        return event

    def on(self, event_name: BotEventName, callback: Callable[[BotEvent], None]):
        """
        Subscribe to a specific event type.

        Args:
            event_name: The event type to subscribe to.
            callback: Function called with the BotEvent when emitted.
        """
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    def history(
        self,
        limit: int = 50,
        event_filter: Optional[BotEventName] = None,
        status_filter: Optional[BotEventStatus] = None,
    ) -> List[BotEvent]:
        """
        Get event history with optional filtering.

        Args:
            limit: Maximum number of events to return.
            event_filter: Only return events of this type.
            status_filter: Only return events with this status.

        Returns:
            List of BotEvent objects, most recent last.
        """
        filtered = self._history

        if event_filter:
            filtered = [e for e in filtered if e.event == event_filter]

        if status_filter:
            filtered = [e for e in filtered if e.status == status_filter]

        return filtered[-limit:]

    def failures(self, limit: int = 20) -> List[BotEvent]:
        """Get recent failure events."""
        return self.history(limit=limit, status_filter=BotEventStatus.FAILED)

    def stats(self) -> Dict[str, Any]:
        """
        Get comprehensive event statistics.

        Returns:
            Dict with counters, failure rates, and subsystem breakdowns.
        """
        total = len(self._history)
        failures = sum(
            1 for e in self._history if e.status == BotEventStatus.FAILED
        )
        completions = sum(
            1 for e in self._history if e.status == BotEventStatus.COMPLETED
        )

        # Subsystem breakdown
        subsystem_counts: Dict[str, int] = {}
        for event in self._history:
            subsystem = event.event.value.split(".")[0]
            subsystem_counts[subsystem] = subsystem_counts.get(subsystem, 0) + 1

        # Failure class breakdown
        failure_classes: Dict[str, int] = {}
        for event in self._history:
            if event.failure_class:
                fc = event.failure_class.value
                failure_classes[fc] = failure_classes.get(fc, 0) + 1

        return {
            "total_events": total,
            "completions": completions,
            "failures": failures,
            "failure_rate": round(failures / total * 100, 1) if total else 0.0,
            "event_counters": dict(self._counters),
            "subsystem_breakdown": subsystem_counts,
            "failure_classes": failure_classes,
        }

    def export_json(self, limit: int = 100) -> str:
        """Export recent events as a JSON array."""
        events = self.history(limit=limit)
        return json.dumps(
            [e.to_dict() for e in events],
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    def clear(self):
        """Clear event history and counters."""
        self._history.clear()
        self._counters.clear()
