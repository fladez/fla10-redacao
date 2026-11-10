"""Carregamento dos documentos editoriais usados em produção e revisão."""

from __future__ import annotations

from pathlib import Path

from fla10_agents.editorial.vault import LocalVaultReader, VaultContext

COMMON_DOCUMENTS = (
    "01 - Manual Editorial/Identidade Editorial.md",
    "01 - Manual Editorial/Apuração e Integridade Factual.md",
    "01 - Manual Editorial/Estilo e Formatação.md",
    "01 - Manual Editorial/Revisão e Controle de Qualidade.md",
    "02 - Operação/Prevenção de Redundância Editorial.md",
    "09 - Modelos/Modelo de Matéria para o Site.md",
)

FORMAT_DOCUMENTS = {
    "onde_assistir": "03 - Formatos/Onde Assistir.md",
    "ultimas_noticias": "03 - Formatos/Matéria de Últimas Notícias.md",
}

DEFAULT_FORMAT_DOCUMENT = "03 - Formatos/Modelo de Matéria para o Site.md"

MAX_CONTEXT_CHARS = 200_000


class WritingContextError(RuntimeError):
    """Contexto editorial ausente ou grande demais para o provedor."""


def format_document(format_name: str) -> str:
    return FORMAT_DOCUMENTS.get(format_name, DEFAULT_FORMAT_DOCUMENT)


def load_writing_context(
    format_name: str,
    vault_root: Path | None = None,
) -> VaultContext:
    reader = LocalVaultReader(vault_root)
    paths = (*COMMON_DOCUMENTS, format_document(format_name))
    context = reader.read(paths)

    total = sum(len(content) for content in context.files.values())
    if total > MAX_CONTEXT_CHARS:
        raise WritingContextError(
            "Os documentos editoriais somam "
            f"{total} caracteres, acima do limite de {MAX_CONTEXT_CHARS}. "
            "Reduza o conjunto antes de chamar o modelo."
        )

    return context


def render_documents(context: VaultContext) -> str:
    blocks = [
        f"### {path}\n\n{content}"
        for path, content in context.files.items()
    ]
    return "\n\n".join(blocks)
