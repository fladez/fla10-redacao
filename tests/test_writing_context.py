"""Confere o contexto de redação contra o vault editorial real.

A suíte monta um vault fake a partir das próprias constantes, então um caminho
errado em ``COMMON_DOCUMENTS`` passa batido aqui e só estoura em produção. Este
teste usa o vault verdadeiro quando existe e pula quando não (CI).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fla10_agents.editorial.vault import default_vault_root
from fla10_agents.writing.context import (
    COMMON_DOCUMENTS,
    DEFAULT_FORMAT_DOCUMENT,
    FORMAT_DOCUMENTS,
    format_document,
    load_writing_context,
)


@pytest.fixture(scope="module")
def real_vault() -> Path:
    root = default_vault_root()
    if not root.is_dir():
        pytest.skip(f"vault editorial ausente: {root}")
    return root


def test_all_context_documents_exist_in_real_vault(real_vault: Path) -> None:
    wanted = tuple(dict.fromkeys((*COMMON_DOCUMENTS, *FORMAT_DOCUMENTS.values())))
    missing = [rel for rel in wanted if not (real_vault / rel).is_file()]
    assert not missing, f"documentos ausentes no vault: {missing}"


@pytest.mark.parametrize("format_name", sorted(FORMAT_DOCUMENTS))
def test_load_writing_context_from_real_vault(real_vault: Path, format_name: str) -> None:
    context = load_writing_context(format_name, real_vault)
    expected = {*COMMON_DOCUMENTS, format_document(format_name)}
    assert set(context.files) == expected


def test_default_format_document_is_not_listed_twice() -> None:
    # Formato desconhecido cai no padrão, que também está em COMMON_DOCUMENTS.
    paths = tuple(dict.fromkeys((*COMMON_DOCUMENTS, format_document("desconhecido"))))
    assert len(paths) == len(set(paths))
    assert paths.count(DEFAULT_FORMAT_DOCUMENT) == 1
