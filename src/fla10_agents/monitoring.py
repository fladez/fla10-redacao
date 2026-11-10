"""Normalização de sinais de monitoramento recebidos de fontes externas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fla10_agents.models import MonitoringSignal


class SignalInputError(ValueError):
    """Sinal de monitoramento inválido."""


def _as_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        signals = payload.get("signals")
        if isinstance(signals, list):
            return list(signals)

    raise SignalInputError(
        "O arquivo deve conter uma lista de sinais ou um objeto com o campo 'signals'."
    )


def signals_from_payload(
    payload: Any,
    *,
    default_provider: str | None = None,
    seen_at: datetime | None = None,
) -> list[MonitoringSignal]:
    """Valida e normaliza sinais, exigindo provedor e identificador externo."""
    now = seen_at or datetime.now(UTC)
    signals: list[MonitoringSignal] = []

    for index, item in enumerate(_as_list(payload), start=1):
        if not isinstance(item, dict):
            raise SignalInputError(f"Sinal {index}: esperado um objeto JSON.")

        data = dict(item)

        provider = data.get("provider") or default_provider
        if not isinstance(provider, str) or not provider.strip():
            raise SignalInputError(
                f"Sinal {index}: informe 'provider' ou use --provider."
            )

        external_id = data.get("external_id")
        if external_id is None or not str(external_id).strip():
            raise SignalInputError(f"Sinal {index}: 'external_id' é obrigatório.")

        data["provider"] = provider.strip()
        data["external_id"] = str(external_id).strip()
        data["last_seen_at"] = now

        try:
            signals.append(MonitoringSignal.model_validate(data))
        except ValueError as exc:
            raise SignalInputError(f"Sinal {index}: {exc}") from exc

    return signals
