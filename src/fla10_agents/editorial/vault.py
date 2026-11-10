"""Leitura local do vault editorial Redacao-Fla10, em modo somente leitura."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fla10_agents.editorial.context_map import BOOTSTRAP_FILES, TASK_DOCUMENTS


class VaultError(RuntimeError):
    """O vault editorial local não está disponível ou está incompleto."""


@dataclass(frozen=True)
class VaultContext:
    root: Path
    commit: str | None
    files: dict[str, str]

    def text_for(self, path: str) -> str:
        try:
            return self.files[path]
        except KeyError as exc:
            raise KeyError(f"Arquivo não carregado do vault: {path}") from exc


def default_vault_root() -> Path:
    configured = os.getenv("EDITORIAL_VAULT_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()

    return Path.home() / "Documents" / "Redacao-Fla10"


class LocalVaultReader:
    """Lê documentos do vault local sem escrever nada nele."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else default_vault_root()

    def _require_root(self) -> None:
        if not self.root.is_dir():
            raise VaultError(
                "Vault editorial não encontrado em "
                f"{self.root}. Defina EDITORIAL_VAULT_PATH ou clone o Redacao-Fla10."
            )

    def head_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        sha = result.stdout.strip()
        return sha if result.returncode == 0 and sha else None

    def read(self, paths: tuple[str, ...] | list[str]) -> VaultContext:
        self._require_root()
        loaded: dict[str, str] = {}
        missing: list[str] = []

        for path in paths:
            file_path = self.root / path
            if not file_path.is_file():
                missing.append(path)
                continue
            try:
                loaded[path] = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise VaultError(f"Falha ao ler {path} no vault: {exc}") from exc

        if missing:
            raise VaultError("Arquivos ausentes no vault: " + ", ".join(missing))

        return VaultContext(root=self.root, commit=self.head_commit(), files=loaded)

    def read_bootstrap(self) -> VaultContext:
        return self.read(BOOTSTRAP_FILES)

    def read_task_context(self, task_type: str) -> VaultContext:
        if task_type not in TASK_DOCUMENTS:
            raise ValueError(f"Tipo de tarefa editorial não mapeado: {task_type}")
        paths = tuple(dict.fromkeys((*BOOTSTRAP_FILES, *TASK_DOCUMENTS[task_type])))
        return self.read(paths)

    def read_pautas(self) -> VaultContext:
        from fla10_agents.editorial.pautas import PAUTA_FILES

        return self.read(PAUTA_FILES)
