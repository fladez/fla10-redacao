import base64
import json

import httpx

from fla10_agents.config import Settings
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
        path = request.url.path
        if path.endswith(f"/commits/main"):
            return _github_response({"sha": commit_sha})
        file_path = path.split("/contents/", maxsplit=1)[1]
        from urllib.parse import unquote
        file_path = unquote(file_path)
        requested.append(file_path)
        encoded = base64.b64encode(files[file_path].encode()).decode()
        return _github_response({
            "type": "file",
            "content": encoded,
            "encoding": "base64",
            "sha": "b" * 40,
            "html_url": f"https://github.com/rcorreas/Redacao-Fla10/blob/main/{file_path}",
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(github_token="test-token")
    with GitHubEditorialReader(settings, client=client) as reader:
        context = reader.read_bootstrap_context()

    assert context.commit_sha == commit_sha
    assert set(context.files) == set(files)
    assert set(requested) == set(files)
    assert context.text_for("AGENTS.md") == "Repository instructions"


def test_read_file_cache_is_scoped_to_commit_and_path() -> None:
    commit_sha = "a" * 40
    count = {"file": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits/main"):
            return _github_response({"sha": commit_sha})
        count["file"] += 1
        encoded = base64.b64encode(b"cached").decode()
        return _github_response({
            "type": "file", "content": encoded, "encoding": "base64",
            "sha": "b" * 40, "html_url": "https://github.com/example/file"
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with GitHubEditorialReader(Settings(github_token="test"), client=client) as reader:
        reader.read_file("README.md", commit_sha)
        reader.read_file("README.md", commit_sha)

    assert count["file"] == 1
