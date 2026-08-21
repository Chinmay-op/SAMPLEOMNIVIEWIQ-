"""
Alert Routing Stub — OI-71
==============================

Layer 6 "Deliver & Act" routing: takes action cards (from OI-69) and
dispatches them to the correct persona via the correct channel.

**Why routing matters** (Architecture §3.3):
A system that sends every alert to every stakeholder trains people to
ignore all of them within a week.  Layer 6 asks "who can actually act
on this specific piece of information?" and sends it only there.

POC channels are **stubs** — they log what *would* be sent.  Each stub
implements the :class:`ChannelBackend` protocol so production channels
(Twilio SMS, SMTP, CMMS API, etc.) can be swapped in later with zero
change to the routing logic.

Routing table
-------------
The ``ROUTING_TABLE`` maps ``(severity, target_role)`` → channels.
This is the documented contract the acceptance criteria requires.

.. list-table::
   :header-rows: 1

   * - Severity
     - Target Role
     - Channels
   * - CRITICAL
     - plant_manager
     - Webhook + Log
   * - CRITICAL
     - operator
     - Webhook + Log
   * - WARNING
     - maintenance_engineer
     - Email + Log
   * - WARNING
     - plant_manager
     - Email + Log
   * - WARNING
     - operator
     - Log
   * - INFO
     - (any)
     - Log

Usage::

    from omniview.dashboard.alert_router import AlertRouter

    router = AlertRouter()
    results = router.route(action_card)
    for r in results:
        print(f"  → {r.channel.value}: {r.status}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from omniview.rules.action_cards import ActionCard

logger = logging.getLogger(__name__)

# ── Timezone ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


# ── Alert Channel enum ──────────────────────────────────────────────────


class AlertChannel(str, Enum):
    """Delivery channel for an alert.

    POC ships LOG, EMAIL, WEBHOOK as stubs.
    SMS and CMMS are reserved for production integration.
    """

    LOG = "log"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"           # reserved — Twilio / MSG91
    CMMS = "cmms"         # reserved — CMMS ticket API


# ── Routing Rule ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutingRule:
    """A single row in the routing table.

    Maps a ``(severity, target_role)`` pair to a list of channels.
    ``description`` is human-readable documentation (for the routing
    table document the acceptance criteria requires).
    """

    severity: str
    target_role: str
    channels: tuple[AlertChannel, ...]
    description: str = ""


# ── Routing Result ──────────────────────────────────────────────────────


@dataclass
class RoutingResult:
    """Outcome of dispatching one card to one channel.

    Attributes
    ----------
    card_id : str
        The action card's dedup-safe ID.
    channel : AlertChannel
        Which channel was used.
    target_role : str
        Which persona was targeted.
    status : str
        ``"sent"`` (stub succeeded) or ``"error"`` with detail.
    detail : str
        Human-readable detail of what the stub emitted.
    timestamp : datetime
        When the dispatch happened.
    """

    card_id: str
    channel: AlertChannel
    target_role: str
    status: str = "sent"
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(IST))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        d = {
            "card_id": self.card_id,
            "channel": self.channel.value,
            "target_role": self.target_role,
            "status": self.status,
            "detail": self.detail,
            "timestamp": self.timestamp.isoformat(),
        }
        return d


# ═══════════════════════════════════════════════════════════════════════
#  ROUTING TABLE — the documented contract
# ═══════════════════════════════════════════════════════════════════════
#
#  Architecture §3.3 defines 4 personas.  For the POC we route to 3
#  (operator, maintenance_engineer, plant_manager) with 3 channel stubs
#  (log, email, webhook).  Finance/ESG is MIS-report-only (future OI-72+).
#
#  The table is intentionally flat — no nested dicts — so it's easy to
#  audit, test, and print as a markdown table for the acceptance criteria.

ROUTING_TABLE: tuple[RoutingRule, ...] = (
    # ── CRITICAL → Webhook + Log ────────────────────────────────────────
    RoutingRule(
        severity="CRITICAL",
        target_role="plant_manager",
        channels=(AlertChannel.WEBHOOK, AlertChannel.LOG),
        description="MD near-miss / critical vibration → push alert to plant manager",
    ),
    RoutingRule(
        severity="CRITICAL",
        target_role="operator",
        channels=(AlertChannel.WEBHOOK, AlertChannel.LOG),
        description="Immediate floor action (breakdown / safety) → push to operator display",
    ),
    RoutingRule(
        severity="CRITICAL",
        target_role="maintenance_engineer",
        channels=(AlertChannel.WEBHOOK, AlertChannel.EMAIL, AlertChannel.LOG),
        description="Critical equipment failure → push + email to maintenance",
    ),
    # ── WARNING → Email + Log ───────────────────────────────────────────
    RoutingRule(
        severity="WARNING",
        target_role="maintenance_engineer",
        channels=(AlertChannel.EMAIL, AlertChannel.LOG),
        description="Lazy-idle / leak / HI decline → email maintenance for scheduled action",
    ),
    RoutingRule(
        severity="WARNING",
        target_role="plant_manager",
        channels=(AlertChannel.EMAIL, AlertChannel.LOG),
        description="Demand trending up / cost warning → email plant manager",
    ),
    RoutingRule(
        severity="WARNING",
        target_role="operator",
        channels=(AlertChannel.LOG,),
        description="Floor-level warning → log only (operator sees dashboard)",
    ),
    # ── INFO → Log only ─────────────────────────────────────────────────
    RoutingRule(
        severity="INFO",
        target_role="plant_manager",
        channels=(AlertChannel.LOG,),
        description="Informational update → log only",
    ),
    RoutingRule(
        severity="INFO",
        target_role="maintenance_engineer",
        channels=(AlertChannel.LOG,),
        description="Informational update → log only",
    ),
    RoutingRule(
        severity="INFO",
        target_role="operator",
        channels=(AlertChannel.LOG,),
        description="Informational update → log only",
    ),
)

# Build a lookup dict for O(1) dispatch
_ROUTING_LOOKUP: dict[tuple[str, str], tuple[AlertChannel, ...]] = {
    (rule.severity, rule.target_role): rule.channels
    for rule in ROUTING_TABLE
}


def lookup_channels(severity: str, target_role: str) -> tuple[AlertChannel, ...]:
    """Look up the channels for a given severity + target_role.

    Falls back to LOG-only for unknown combinations.
    """
    return _ROUTING_LOOKUP.get(
        (severity, target_role),
        (AlertChannel.LOG,),  # safe default
    )


# ═══════════════════════════════════════════════════════════════════════
#  CHANNEL BACKENDS (stubs)
# ═══════════════════════════════════════════════════════════════════════


@runtime_checkable
class ChannelBackend(Protocol):
    """Protocol that every channel backend must satisfy.

    Production implementations will send real SMS/email/HTTP;
    POC stubs log what *would* be sent.
    """

    channel: AlertChannel

    def send(self, card: ActionCard) -> RoutingResult:
        """Dispatch one action card via this channel."""
        ...


# ── Email recipient map ─────────────────────────────────────────────────

_DEFAULT_EMAIL_RECIPIENTS: dict[str, str] = {
    "plant_manager": "plant.manager@example.com",
    "maintenance_engineer": "maintenance@example.com",
    "operator": "floor.ops@example.com",
    "finance": "finance@example.com",
}


# ── LogChannel ──────────────────────────────────────────────────────────


class LogChannel:
    """Stub: emits structured Python log for every routed alert.

    Always active — every alert gets logged regardless of other channels.
    """

    channel = AlertChannel.LOG

    def send(self, card: ActionCard) -> RoutingResult:
        """Log the alert in structured format."""
        log_entry = {
            "alert_routing": "LOG",
            "card_id": card.card_id,
            "severity": card.severity,
            "event_type": card.event_type,
            "device_id": card.device_id,
            "target_role": card.target_role,
            "title": card.title,
            "timestamp": (
                card.timestamp.isoformat()
                if hasattr(card.timestamp, "isoformat")
                else str(card.timestamp)
            ),
        }

        if card.severity == "CRITICAL":
            logger.warning("ALERT ROUTED [LOG] %s", json.dumps(log_entry))
        else:
            logger.info("ALERT ROUTED [LOG] %s", json.dumps(log_entry))

        return RoutingResult(
            card_id=card.card_id,
            channel=AlertChannel.LOG,
            target_role=card.target_role,
            status="sent",
            detail=f"Logged: {card.severity} {card.event_type} → {card.target_role}",
        )


# ── EmailChannel ────────────────────────────────────────────────────────


class EmailChannel:
    """Stub: logs what *would* be emailed.

    In production, replace with SMTP / SendGrid / SES.
    """

    channel = AlertChannel.EMAIL

    def __init__(
        self,
        recipient_map: dict[str, str] | None = None,
    ) -> None:
        self._recipients = recipient_map or _DEFAULT_EMAIL_RECIPIENTS

    def send(self, card: ActionCard) -> RoutingResult:
        """Log the mock email dispatch."""
        recipient = self._recipients.get(
            card.target_role,
            f"{card.target_role}@example.com",
        )
        subject = f"[OmniView IQ] [{card.severity}] {card.title}"
        body_preview = card.summary[:120] + ("..." if len(card.summary) > 120 else "")

        email_mock = {
            "alert_routing": "EMAIL",
            "to": recipient,
            "subject": subject,
            "body_preview": body_preview,
            "card_id": card.card_id,
            "device_id": card.device_id,
        }

        logger.info("ALERT ROUTED [EMAIL] %s", json.dumps(email_mock))

        return RoutingResult(
            card_id=card.card_id,
            channel=AlertChannel.EMAIL,
            target_role=card.target_role,
            status="sent",
            detail=f"Email stub → {recipient}: {subject}",
        )


# ── WebhookChannel ──────────────────────────────────────────────────────


class WebhookChannel:
    """Stub: logs what *would* be POSTed to a webhook endpoint.

    In production, replace with ``httpx.post()`` or ``requests.post()``.
    """

    channel = AlertChannel.WEBHOOK

    def __init__(self, url: str = "http://localhost:9999/alerts") -> None:
        self._url = url

    def send(self, card: ActionCard) -> RoutingResult:
        """Log the mock webhook POST."""
        payload = {
            "card_id": card.card_id,
            "severity": card.severity,
            "event_type": card.event_type,
            "title": card.title,
            "summary": card.summary,
            "recommended_action": card.recommended_action,
            "target_role": card.target_role,
            "device_id": card.device_id,
            "rupee_impact": card.rupee_impact,
            "urgency_window": card.urgency_window,
            "timestamp": (
                card.timestamp.isoformat()
                if hasattr(card.timestamp, "isoformat")
                else str(card.timestamp)
            ),
        }

        webhook_mock = {
            "alert_routing": "WEBHOOK",
            "url": self._url,
            "method": "POST",
            "payload": payload,
        }

        logger.info("ALERT ROUTED [WEBHOOK] %s", json.dumps(webhook_mock))

        return RoutingResult(
            card_id=card.card_id,
            channel=AlertChannel.WEBHOOK,
            target_role=card.target_role,
            status="sent",
            detail=f"Webhook stub → POST {self._url} ({card.severity} {card.event_type})",
        )


# ═══════════════════════════════════════════════════════════════════════
#  ALERT ROUTER
# ═══════════════════════════════════════════════════════════════════════


class AlertRouter:
    """Stateless alert router: ActionCard → channel dispatch.

    Looks up the routing table to determine which channels each card
    should be dispatched to, then calls the corresponding channel backend.

    The router is stateless — it doesn't cache or queue.  Suitable for
    both batch (dashboard scan) and real-time (rule engine callback) use.

    Parameters
    ----------
    enabled : bool
        Feature flag.  When ``False``, ``route()`` returns an empty list
        and logs a debug message.  Default: ``True``.
    webhook_url : str
        Webhook endpoint for the :class:`WebhookChannel` stub.
    email_recipients : dict[str, str] or None
        Role → email address map for the :class:`EmailChannel` stub.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        webhook_url: str = "http://localhost:9999/alerts",
        email_recipients: dict[str, str] | None = None,
    ) -> None:
        self._enabled = enabled

        # Instantiate channel backends
        self._backends: dict[AlertChannel, ChannelBackend] = {
            AlertChannel.LOG: LogChannel(),
            AlertChannel.EMAIL: EmailChannel(recipient_map=email_recipients),
            AlertChannel.WEBHOOK: WebhookChannel(url=webhook_url),
        }

    @property
    def enabled(self) -> bool:
        """Whether routing is active."""
        return self._enabled

    def route(self, card: ActionCard) -> list[RoutingResult]:
        """Route a single action card to the appropriate channels.

        Parameters
        ----------
        card : ActionCard
            The card to route (must have ``severity`` and ``target_role``).

        Returns
        -------
        list[RoutingResult]
            One result per channel the card was dispatched to.
        """
        if not self._enabled:
            logger.debug(
                "Alert routing disabled — skipping card %s", card.card_id
            )
            return []

        channels = lookup_channels(card.severity, card.target_role)
        results: list[RoutingResult] = []

        for channel in channels:
            backend = self._backends.get(channel)
            if backend is None:
                logger.warning(
                    "No backend for channel %s — skipping", channel.value
                )
                continue

            try:
                result = backend.send(card)
                results.append(result)
            except Exception:
                logger.exception(
                    "Failed to dispatch card %s via %s",
                    card.card_id,
                    channel.value,
                )
                results.append(
                    RoutingResult(
                        card_id=card.card_id,
                        channel=channel,
                        target_role=card.target_role,
                        status="error",
                        detail=f"Exception in {channel.value} backend",
                    )
                )

        logger.info(
            "Routed card %s (%s/%s) → %s",
            card.card_id,
            card.severity,
            card.target_role,
            [r.channel.value for r in results],
        )

        return results

    def route_batch(
        self,
        cards: list[ActionCard],
    ) -> list[RoutingResult]:
        """Route multiple action cards.

        Parameters
        ----------
        cards : list[ActionCard]
            Cards to route.

        Returns
        -------
        list[RoutingResult]
            All routing results, flattened.
        """
        all_results: list[RoutingResult] = []

        for card in cards:
            try:
                results = self.route(card)
                all_results.extend(results)
            except Exception:
                logger.exception(
                    "Unexpected error routing card %s", card.card_id
                )
                continue

        logger.info(
            "Batch routed %d cards → %d dispatches",
            len(cards),
            len(all_results),
        )

        return all_results


# ═══════════════════════════════════════════════════════════════════════
#  ROUTING TABLE DOCUMENTATION HELPER
# ═══════════════════════════════════════════════════════════════════════


def get_routing_table_markdown() -> str:
    """Return the routing table as a markdown table string.

    Used for the worklog and acceptance criteria documentation.
    """
    lines = [
        "| Severity | Target Role | Channels | Description |",
        "|----------|-------------|----------|-------------|",
    ]
    for rule in ROUTING_TABLE:
        channels_str = ", ".join(ch.value for ch in rule.channels)
        lines.append(
            f"| {rule.severity} | {rule.target_role} | {channels_str} | {rule.description} |"
        )
    return "\n".join(lines)
