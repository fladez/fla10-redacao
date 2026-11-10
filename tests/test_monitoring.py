from datetime import UTC, datetime

import pytest

from fla10_agents.monitoring import SignalInputError, signals_from_payload

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def signal_payload() -> dict[str, object]:
    return {
        "provider": "teste",
        "external_id": "sig-1",
        "title": "Flamengo treina",
        "published_at": "2026-11-10T09:00:00-03:00",
    }


def test_signals_from_payload_accepts_list_and_sets_last_seen_at() -> None:
    signals = signals_from_payload([signal_payload()], seen_at=NOW)

    assert len(signals) == 1
    assert signals[0].last_seen_at == NOW
    assert signals[0].published_at.tzinfo is not None


def test_signals_from_payload_accepts_wrapper_and_default_provider() -> None:
    payload = signal_payload()
    payload.pop("provider")

    signals = signals_from_payload(
        {"signals": [payload]},
        default_provider="monitor",
        seen_at=NOW,
    )

    assert signals[0].provider == "monitor"


def test_signals_from_payload_requires_external_id() -> None:
    payload = signal_payload()
    payload.pop("external_id")

    with pytest.raises(SignalInputError, match="external_id"):
        signals_from_payload([payload], seen_at=NOW)


def test_signals_from_payload_requires_provider() -> None:
    payload = signal_payload()
    payload.pop("provider")

    with pytest.raises(SignalInputError, match="provider"):
        signals_from_payload([payload], seen_at=NOW)


def test_signals_from_payload_rejects_invalid_shape() -> None:
    with pytest.raises(SignalInputError, match="lista de sinais"):
        signals_from_payload({"items": []}, seen_at=NOW)

    with pytest.raises(SignalInputError, match="objeto JSON"):
        signals_from_payload(["texto"], seen_at=NOW)
