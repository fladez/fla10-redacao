import base64
from urllib.parse import unquote

import httpx

from fla10_agents.config import Settings
from fla10_agents.editorial.context_map import BOOTSTRAP_FILES
from fla10_agents.editorial.github_reader import GitHubEditorialReader


def _github_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_read_bootstrap_context_uses_one_commit_for_all_files() -> None:
    commit_sha = "a" * 40

    files = {
        "AGENTS.md": "Repository instructions",
        "README.md": "Editorial repository",
        "00 - Sistema/Índice.md": "Index",
        "00 - Sistema/Protocolo de Operação da IA.md": "Protocol",
    }

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"

        path = request.url.path

        if path.endswith("/commits/main"):
            return _github_response({"sha": commit_sha})

        file_path = unquote(path.split("/contents/", maxsplit=1)[1])
        requested.append(file_path)

        encoded = base64.b64encode(files[file_path].encode()).decode()

        return _github_response(
            {
                "type": "file",
                "content": encoded,
                "encoding": "base64",
                "sha": "b" * 40,
                "html_url": f"https://github.com/rcorreas/Redacao-Fla10/blob/main/{file_path}",
            }
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(github_token="test-token")

    with GitHubEditorialReader(settings, client=client) as reader:
        context = reader.read_bootstrap_context()

    client.close()

    assert context.commit_sha == commit_sha
    assert set(context.files) == set(files)
    assert set(requested) == set(files)
    assert context.text_for("AGENTS.md") == "Repository instructions"


def test_read_file_cache_is_scoped_to_commit_and_path() -> None:
    commit_sha = "a" * 40
    count = {"file": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test"

        if request.url.path.endswith("/commits/main"):
            return _github_response({"sha": commit_sha})

        count["file"] += 1
        encoded = base64.b64encode(b"cached").decode()

        return _github_response(
            {
                "type": "file",
                "content": encoded,
                "encoding": "base64",
                "sha": "b" * 40,
                "html_url": "https://github.com/example/file",
            }
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with GitHubEditorialReader(
        Settings(github_token="test"),
        client=client,
    ) as reader:
        reader.read_file("README.md", commit_sha)
        reader.read_file("README.md", commit_sha)

    client.close()

    assert count["file"] == 1


def test_read_calendar_context_includes_reliability_documents() -> None:
    commit_sha = "c" * 40

    calendar_files = (
        "02 - Operação/Fluxo de Produção.md",
        "02 - Operação/Gestão de Pautas.md",
        "06 - Pautas/Painel de Pautas.md",
        "02 - Operação/Pesquisa e Fontes.md",
        "08 - Fontes e Referências/Critérios de Confiabilidade.md",
    )

    expected_files = set(BOOTSTRAP_FILES) | set(calendar_files)
    requested: list[str] = []
    commit_requests = {"count": 0}

    files = {path: f"Conteúdo de teste: {path}" for path in expected_files}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test"

        path = request.url.path

        if path.endswith("/commits/main"):
            commit_requests["count"] += 1
            return _github_response({"sha": commit_sha})

        file_path = unquote(path.split("/contents/", maxsplit=1)[1])
        requested.append(file_path)

        assert file_path in files

        encoded = base64.b64encode(files[file_path].encode("utf-8")).decode()

        return _github_response(
            {
                "type": "file",
                "content": encoded,
                "encoding": "base64",
                "sha": "d" * 40,
                "html_url": f"https://github.com/rcorreas/Redacao-Fla10/blob/main/{file_path}",
            }
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with GitHubEditorialReader(
        Settings(github_token="test"),
        client=client,
    ) as reader:
        context = reader.read_task_context("calendar")

    client.close()

    assert context.commit_sha == commit_sha
    assert commit_requests["count"] == 1
    assert set(context.files) == expected_files
    assert set(requested) == expected_files
    assert len(requested) == len(expected_files)

    assert (
        context.text_for("02 - Operação/Pesquisa e Fontes.md")
        == "Conteúdo de teste: 02 - Operação/Pesquisa e Fontes.md"
    )

    assert context.text_for("08 - Fontes e Referências/Critérios de Confiabilidade.md") == (
        "Conteúdo de teste: 08 - Fontes e Referências/Critérios de Confiabilidade.md"
    )
