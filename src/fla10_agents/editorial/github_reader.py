"""Adaptador somente leitura para consultar o vault editorial no GitHub."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from fla10_agents.config import Settings
from fla10_agents.editorial.context_map import BOOTSTRAP_FILES, TASK_DOCUMENTS


class EditorialSourceError(RuntimeError):
    """Erro ao ler a fonte editorial canônica."""


@dataclass(frozen=True)
class EditorialFile:
    path: str
    content: str
    blob_sha: str
    commit_sha: str
    html_url: str


@dataclass(frozen=True)
class EditorialContext:
    repository: str
    branch: str
    commit_sha: str
    files: dict[str, EditorialFile]

    def text_for(self, path: str) -> str:
        try:
            return self.files[path].content
        except KeyError as exc:
            raise KeyError(f"Arquivo não carregado no contexto: {path}") from exc


class GitHubEditorialReader:
    """Leitor da API GitHub com escopo estritamente de leitura."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=20.0)
        self._owns_client = client is None
        self._client.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self._cache: dict[tuple[str, str], EditorialFile] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GitHubEditorialReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def repository(self) -> str:
        return self._settings.editorial_repo

    @property
    def branch(self) -> str:
        return self._settings.editorial_branch

    def _get_json(self, endpoint: str, params: dict[str, str] | None = None) -> dict:
        url = f"{self._settings.github_api_url}/{endpoint.lstrip('/')}"
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EditorialSourceError(
                f"Falha ao consultar a fonte editorial no GitHub ({endpoint}): {exc}"
            ) from exc

    def head_commit(self) -> str:
        owner, name = self.repository.split("/", maxsplit=1)
        data = self._get_json(f"repos/{owner}/{name}/commits/{quote(self.branch, safe='')}")
        sha = data.get("sha")
        if not isinstance(sha, str) or not sha:
            raise EditorialSourceError("GitHub não retornou o SHA do commit editorial.")
        return sha

    def read_file(self, path: str, commit_sha: str | None = None) -> EditorialFile:
        revision = commit_sha or self.head_commit()
        cache_key = (revision, path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        owner, name = self.repository.split("/", maxsplit=1)
        encoded_path = quote(path, safe="/")
        data = self._get_json(
            f"repos/{owner}/{name}/contents/{encoded_path}",
            params={"ref": revision},
        )
        if data.get("type") != "file":
            raise EditorialSourceError(f"O caminho não é um arquivo: {path}")

        encoded_content = data.get("content", "")
        if data.get("encoding") != "base64" or not encoded_content:
            raise EditorialSourceError(
                f"GitHub não forneceu conteúdo base64 legível para {path}. "
                "O arquivo pode exigir leitura pela API Git Blobs."
            )
        try:
            content = base64.b64decode(encoded_content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise EditorialSourceError(f"Conteúdo inválido ou não UTF-8 em {path}.") from exc

        result = EditorialFile(
            path=path,
            content=content,
            blob_sha=str(data.get("sha", "")),
            commit_sha=revision,
            html_url=str(data.get("html_url", "")),
        )
        self._cache[cache_key] = result
        return result

    def read_files(
        self,
        paths: tuple[str, ...] | list[str],
        commit_sha: str | None = None,
    ) -> EditorialContext:
        revision = commit_sha or self.head_commit()
        loaded = {path: self.read_file(path, revision) for path in paths}
        return EditorialContext(
            repository=self.repository,
            branch=self.branch,
            commit_sha=revision,
            files=loaded,
        )

    def read_bootstrap_context(self) -> EditorialContext:
        return self.read_files(BOOTSTRAP_FILES)

    def read_task_context(self, task_type: str) -> EditorialContext:
        if task_type not in TASK_DOCUMENTS:
            raise ValueError(f"Tipo de tarefa editorial não mapeado: {task_type}")
        revision = self.head_commit()
        paths = tuple(dict.fromkeys((*BOOTSTRAP_FILES, *TASK_DOCUMENTS[task_type])))
        return self.read_files(paths, revision)
