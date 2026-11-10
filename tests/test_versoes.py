"""Testes da separação das versões geradas pelo revisor."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import versoes

SAIDA_MARCADA = """\
<!-- VERSAO:1 -->
# Título factual

Corpo da versão 1.

<!-- VERSAO:2 -->
# Título tático

Corpo da versão 2.
"""

SAIDA_SEM_MARCADOR = """\
# FLA10 News

## Versão 1 — Notícia factual

Corpo 1.

## Versão 2 — Análise tática

Corpo 2.
"""


def test_separa_pelo_marcador():
    partes = versoes.separar_versoes(SAIDA_MARCADA)

    assert [numero for numero, _ in partes] == [1, 2]
    assert "Corpo da versão 1." in partes[0][1]
    assert partes[1][1].startswith("# Título tático")


def test_cai_para_titulo_quando_sem_marcador():
    partes = versoes.separar_versoes(SAIDA_SEM_MARCADOR)

    assert [numero for numero, _ in partes] == [1, 2]
    assert "Corpo 2." in partes[1][1]


def test_texto_sem_estrutura_nao_inventa_versao():
    assert versoes.separar_versoes("texto solto sem título") == []


def test_salvar_grava_um_arquivo_por_versao(tmp_path):
    pasta = versoes.salvar_versoes(
        SAIDA_MARCADA,
        versoes.separar_versoes(SAIDA_MARCADA),
        base=tmp_path,
        quando=datetime(2026, 11, 10, 15, 30),
    )

    assert pasta.name == "redacao-2026-11-10-1530"
    assert (pasta / "completa.md").exists()
    assert (pasta / "versao-1.md").read_text(encoding="utf-8").startswith("# Título factual")
    assert (pasta / "versao-2.md").exists()
    assert not (pasta / "versao-3.md").exists()
