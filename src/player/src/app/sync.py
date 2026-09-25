"""A small NTP-style bridge from the local monotonic clock to server time."""

import math
from collections import deque
from time import monotonic


def finite_number(value) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


class ServerClock:
    """Use the least-delayed recent exchange, independent of local wall time.

    As in BeatSync, subtract the server's processing time from the round trip
    and select the lowest-RTT measurement: queued packets only add delay.
    Network asymmetry and unreported speaker latency still limit accuracy.
    """

    MIN_SAMPLES = 3
    # At the 2 s heartbeat cadence this bounds sample age to <8 s, keeping
    # oscillator bias below 0.8 ms at 100 ppm instead of accumulating drift.
    WINDOW_SECONDS = 6.0
    MAX_ROUND_TRIP = 1.0
    MAX_EXCHANGE_SECONDS = 5.0

    def __init__(self):
        self._samples = deque(maxlen=32)
        self._offset = None
        self._last_send = None
        self._samples_seen = 0

    @property
    def ready(self) -> bool:
        return self._offset is not None

    def reset(self, *, keep_estimate: bool = True) -> None:
        """Relearn after reconnect, optionally retaining playback holdover."""
        self._samples.clear()
        self._last_send = None
        self._samples_seen = 0
        if not keep_estimate:
            self._offset = None

    def observe(self, client_send, server_receive, server_send, client_receive) -> bool:
        """Accept four timestamps in seconds; client timestamps are monotonic."""
        values = (client_send, server_receive, server_send, client_receive)
        if not all(finite_number(value) for value in values):
            return False
        elapsed = client_receive - client_send
        processing = server_send - server_receive
        round_trip = elapsed - processing
        if (
            client_send < 0
            or server_receive <= 0
            or not 0 <= elapsed <= self.MAX_EXCHANGE_SECONDS
            or processing < 0
            # Epoch float rounding can make a zero-delay exchange slightly negative.
            or not -0.000001 <= round_trip <= self.MAX_ROUND_TRIP
            or (self._last_send is not None and client_send <= self._last_send)
        ):
            return False
        self._last_send = client_send
        self._samples_seen = min(self._samples_seen + 1, self.MIN_SAMPLES)
        offset = ((server_receive - client_send) + (server_send - client_receive)) / 2
        self._samples.append((client_receive, max(0.0, round_trip), offset))
        while self._samples and client_receive - self._samples[0][0] > self.WINDOW_SECONDS:
            self._samples.popleft()
        # Only bootstrap needs three observations. After a gap, even one fresh
        # sample is better than retaining an old mapping indefinitely.
        if self._samples_seen >= self.MIN_SAMPLES:
            # Prefer the newer sample when delays tie, so oscillator drift tracks.
            self._offset = min(self._samples, key=lambda sample: (sample[1], -sample[0]))[2]
        return True

    def server_time(self, monotonic_seconds: float | None = None) -> float | None:
        """Map a local time (including an audio DAC deadline) onto server time."""
        offset = self._offset
        if offset is None:
            return None
        return (monotonic() if monotonic_seconds is None else monotonic_seconds) + offset
