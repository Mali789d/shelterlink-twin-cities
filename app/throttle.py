"""Bound paid reply traffic per sender.

Every non-keyword SMS reply costs money once a real number is attached. A
malfunctioning handset or an abusive sender can otherwise run up unbounded
inbound and reply charges, so the webhook answers at most a fixed number of
service replies per sender inside a sliding window and returns empty TwiML
past the limit. Consent keywords (STOP, START, HELP) are never throttled:
carriers require them to work every time.

Prototype scope: windows live in this process, like the in-memory opt-out
store used outside production. A multi-instance deployment needs a shared
store before launch; until then the limit applies per instance.
"""

import os
import time
from collections import OrderedDict

# Five service replies per sender per hour covers real use (a ZIP, a retry,
# a second category) while capping what a runaway sender can cost.
DEFAULT_MAX_REPLIES = 5
DEFAULT_WINDOW_SECONDS = 3600

# An unbounded map of senders is itself a memory target; evict the least
# recently active sender past a generous ceiling.
DEFAULT_MAX_TRACKED_SENDERS = 10_000


def _positive_int(env, name: str, default: int) -> int:
    try:
        value = int(env.get(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


class ReplyThrottle:
    """Sliding-window per-sender reply budget with an injectable clock."""

    def __init__(self, max_replies: int = DEFAULT_MAX_REPLIES,
                 window_seconds: int = DEFAULT_WINDOW_SECONDS,
                 max_tracked_senders: int = DEFAULT_MAX_TRACKED_SENDERS,
                 now=time.monotonic) -> None:
        if max_replies < 1 or window_seconds < 1 or max_tracked_senders < 1:
            raise ValueError("throttle limits must be positive")
        self._max_replies = max_replies
        self._window = window_seconds
        self._max_tracked = max_tracked_senders
        self._now = now
        self._hits: OrderedDict[str, list[float]] = OrderedDict()

    @classmethod
    def from_env(cls, env=None) -> "ReplyThrottle":
        """Read SHELTERLINK_SMS_REPLY_LIMIT and _REPLY_WINDOW_SECONDS.

        Missing or invalid values fall back to the defaults; configuration is
        read once at startup, like the other webhook settings.
        """
        env = os.environ if env is None else env
        return cls(
            max_replies=_positive_int(
                env, "SHELTERLINK_SMS_REPLY_LIMIT", DEFAULT_MAX_REPLIES),
            window_seconds=_positive_int(
                env, "SHELTERLINK_SMS_REPLY_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS),
        )

    def allow(self, sender: str) -> bool:
        """Record one paid reply for sender; False when the window is full."""
        now = self._now()
        hits = self._hits.get(sender)
        if hits is None:
            hits = []
            self._hits[sender] = hits
        else:
            self._hits.move_to_end(sender)
        cutoff = now - self._window
        hits[:] = [stamp for stamp in hits if stamp > cutoff]
        if len(hits) >= self._max_replies:
            return False
        hits.append(now)
        while len(self._hits) > self._max_tracked:
            self._hits.popitem(last=False)
        return True
