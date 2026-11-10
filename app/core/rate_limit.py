"""In-process sliding-window rate limiter.

State lives in the memory of one process, so with several API replicas every replica counts
separately. For a shared limit put a limiter in front of the API (reverse proxy) or back this
class with Redis; the interface (`check`) is deliberately small to make that swap easy.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

_PRUNE_THRESHOLD = 10_000


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Register one attempt for `key`.

        Returns None when the attempt is allowed, otherwise the number of seconds
        until the oldest attempt leaves the window. Rejected attempts are not counted.
        """
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()

        if len(hits) >= limit:
            return window_seconds - (now - hits[0])

        hits.append(now)
        if len(self._hits) > _PRUNE_THRESHOLD:
            self._prune(now, window_seconds)
        return None

    def reset(self) -> None:
        self._hits.clear()

    def _prune(self, now: float, window_seconds: float) -> None:
        stale = [
            k for k, hits in self._hits.items() if not hits or now - hits[-1] >= window_seconds
        ]
        for key in stale:
            del self._hits[key]


auth_limiter = SlidingWindowRateLimiter()
