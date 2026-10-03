"""A small circuit breaker.

How this works:

* CLOSED: calls pass. Consecutive failures are counted; reaching the threshold
  opens the circuit.
* OPEN: calls are rejected immediately, so a struggling provider gets time to
  recover and users get a fast error instead of waiting for a timeout.
* HALF_OPEN: after ``reset_seconds`` one trial call is let through. Success
  closes the circuit; failure opens it again.

State is per process. With N replicas each one learns about an outage on its
own (after ``threshold`` failures); sharing breaker state through Redis is a
documented future improvement.
"""

import time
from collections.abc import Callable
from enum import IntEnum


class CircuitState(IntEnum):
    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        reset_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        on_state_change: Callable[[CircuitState], None] | None = None,
    ) -> None:
        self._threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._clock = clock
        self._on_state_change = on_state_change
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_flight = False

    @property
    def state(self) -> CircuitState:
        return self._state

    def _set_state(self, state: CircuitState) -> None:
        if state is not self._state:
            self._state = state
            if self._on_state_change:
                self._on_state_change(state)

    def allow(self) -> bool:
        """Return True if a call may be attempted now."""
        if self._state is CircuitState.CLOSED:
            return True
        if self._state is CircuitState.OPEN:
            if self._clock() - self._opened_at < self._reset_seconds:
                return False
            self._set_state(CircuitState.HALF_OPEN)
            self._trial_in_flight = False
        # HALF_OPEN: admit exactly one trial call at a time.
        if self._trial_in_flight:
            return False
        self._trial_in_flight = True
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._trial_in_flight = False
        self._set_state(CircuitState.CLOSED)

    def record_failure(self) -> None:
        self._trial_in_flight = False
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self._threshold:
            self._open()

    def release_trial(self) -> None:
        """A trial call ended without saying anything about provider health."""
        self._trial_in_flight = False

    def _open(self) -> None:
        self._failures = 0
        self._opened_at = self._clock()
        self._set_state(CircuitState.OPEN)
