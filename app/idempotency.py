"""Idempotent SMS webhook processing across Twilio redeliveries.

Twilio's delivery of inbound-message webhooks is at least once: it retries
failed webhook attempts (by default once, on connection timeout; a response
that takes longer than the read timeout also triggers a fresh attempt) and
every attempt of the same inbound message carries the same ``MessageSid``.
This module caches each successful reply so a redelivery returns the
identical response instead of being processed again.

What this guarantees, per process, within the cache window:

- one computation per message: geocoding, search and consent work run once;
- one reply-throttle slot per message: redeliveries never double-spend budget;
- one response body per message: redeliveries cannot diverge.

What it cannot guarantee: exactly-once outbound SMS. Twilio sends a reply for
every TwiML ``<Message>`` response it processes, and it does not dedupe those
sends by the inbound MessageSid. If Twilio processes responses from two
attempts (for example a late response racing its retry), or a redelivery
arrives after this cache expired or the process restarted, the sender can
receive the reply twice. Those windows are provider-side or deployment-side;
keep them small by responding well inside Twilio's 15-second read timeout.

Replays are bound to the sender and body of the original request: a request
carrying a known ``MessageSid`` with different content is processed fresh,
never answered with someone else's cached reply. Entries expire after four
hours, far beyond Twilio's seconds-long automatic retry window, and the
oldest entries are evicted past 10,000 so the cache cannot become a memory
target. Failed deliveries (4xx/5xx) are never cached, so a retry after an
outage is processed fresh and the sender still gets help.

Prototype scope: the cache lives in this process, like the development
opt-out store and the reply throttle. The path from cache lookup to cache
store is synchronous, so redeliveries cannot interleave inside one process;
a multi-instance deployment needs a shared store before launch.
"""

import time
from collections import OrderedDict

# Twilio's automatic retries play out within seconds; four hours covers the
# realistic redelivery window without holding replies forever.
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
        self._entries: OrderedDict[str, tuple[float, str, str, str]] = OrderedDict()

    def get(self, message_sid: str, sender: str, body: str) -> str | None:
        """The stored reply for a redelivery of the same request, or None."""
        entry = self._entries.get(message_sid)
        if entry is None:
            return None
        expires_at, cached_sender, cached_body, reply = entry
        if self._now() >= expires_at:
            del self._entries[message_sid]
            return None
        if (sender, body) != (cached_sender, cached_body):
            # A reused or spoofed ID must never replay someone else's reply.
            return None
        self._entries.move_to_end(message_sid)
        return reply

    def put(self, message_sid: str, sender: str, body: str, reply: str) -> None:
        """Store a successful reply, bound to the request that earned it."""
        self._entries[message_sid] = (self._now() + self._ttl, sender, body, reply)
        self._entries.move_to_end(message_sid)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
