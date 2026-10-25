"""Exactly-once SMS replies over Twilio's at-least-once webhook delivery.

Twilio retries webhooks after 5xx responses and connection failures, and a
retry of a delivery whose 200 response was lost on the wire would otherwise
send the user a second, possibly different paid reply. The webhook therefore
caches each successful reply by its ``MessageSid`` and answers a redelivery
with the identical response. Failed deliveries (4xx/5xx) are never cached,
so a retry after an outage is processed fresh and the user still gets help.

Prototype scope: the cache lives in this process, like the development
opt-out store and the reply throttle. A multi-instance deployment needs a
shared store before launch; until then a redelivery that lands on a
different instance is processed again.
"""

import time
from collections import OrderedDict

# Twilio's webhook retries play out over minutes to hours; four hours covers
# the realistic redelivery window without holding replies forever.
DEFAULT_TTL_SECONDS = 4 * 3600

# Replies are small, but an unbounded map of message IDs is still a memory
# target; evict the oldest entries past a generous ceiling.
DEFAULT_MAX_ENTRIES = 10_000


class ReplyCache:
    """Bounded TTL cache of TwiML replies keyed by MessageSid."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 max_entries: int = DEFAULT_MAX_ENTRIES,
                 now=time.monotonic) -> None:
        if ttl_seconds < 1 or max_entries < 1:
            raise ValueError("cache limits must be positive")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._now = now
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, message_sid: str) -> str | None:
        """The stored reply for a redelivery, or None."""
        entry = self._entries.get(message_sid)
        if entry is None:
            return None
        expires_at, body = entry
        if self._now() >= expires_at:
            del self._entries[message_sid]
            return None
        self._entries.move_to_end(message_sid)
        return body

    def put(self, message_sid: str, body: str) -> None:
        """Store a successful reply for future redeliveries."""
        self._entries[message_sid] = (self._now() + self._ttl, body)
        self._entries.move_to_end(message_sid)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
