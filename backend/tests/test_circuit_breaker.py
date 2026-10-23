from unittest.mock import patch

from ai.circuit_breaker import CircuitBreaker


def test_circuit_breaker_opens_then_recovers_after_cooldown():
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10)
    breaker.record_failure()
    assert breaker.allow_request() is True
    breaker.record_failure()
    assert breaker.allow_request() is False

    with patch("ai.circuit_breaker.time.monotonic", return_value=breaker.opened_at + 11):
        assert breaker.allow_request() is True
