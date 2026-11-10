"""Requisições HTTP com número limitado de tentativas."""

import time
from typing import Any

import httpx

RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def get_with_retries(
    client: httpx.Client,
    url: str,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    **kwargs: Any,
) -> httpx.Response:
    """Executa um GET e repete apenas falhas transitórias.

    Erros de transporte e respostas 429/5xx são tentados de novo com espera
    crescente. A última resposta é devolvida para que o chamador aplique
    `raise_for_status` e preserve a mensagem original.
    """
    if attempts < 1:
        raise ValueError("attempts deve ser maior ou igual a 1.")

    last_error: httpx.TransportError | None = None

    for attempt in range(attempts):
        try:
            response = client.get(url, **kwargs)
        except httpx.TransportError as exc:
            last_error = exc
        else:
            if response.status_code not in RETRY_STATUS_CODES or attempt == attempts - 1:
                return response
            last_error = None

        if attempt < attempts - 1:
            time.sleep(base_delay * (2**attempt))

    if last_error is not None:
        raise last_error

    raise httpx.TransportError(f"Não foi possível concluir a requisição: {url}")
