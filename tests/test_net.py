import httpx
import pytest

from fla10_agents.net import get_with_retries


def make_client(responses: list[int]) -> tuple[httpx.Client, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        status = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json={})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_retries_transient_status_until_success() -> None:
    client, calls = make_client([503, 502, 200])

    with client:
        response = get_with_retries(client, "https://example.test/pdf", base_delay=0)

    assert response.status_code == 200
    assert len(calls) == 3


def test_returns_last_response_when_attempts_are_exhausted() -> None:
    client, calls = make_client([503, 503])

    with client:
        response = get_with_retries(
            client,
            "https://example.test/pdf",
            attempts=2,
            base_delay=0,
        )

    assert response.status_code == 503
    assert len(calls) == 2


def test_does_not_retry_client_errors() -> None:
    client, calls = make_client([404])

    with client:
        response = get_with_retries(client, "https://example.test/pdf", base_delay=0)

    assert response.status_code == 404
    assert len(calls) == 1


def test_raises_transport_error_after_attempts() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("sem rede", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with client, pytest.raises(httpx.ConnectError):
        get_with_retries(client, "https://example.test/pdf", attempts=3, base_delay=0)

    assert attempts == 3
