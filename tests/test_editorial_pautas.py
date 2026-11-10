from datetime import date

from fla10_agents.editorial.pautas import parse_pauta_documents, parse_pautas

PAINEL = """# Painel de Pautas

## Pautas mencionadas para 14 de outubro de 2026

### Estudantes também tem problemas na defesa
- **Estado:** confirmar com o responsável editorial.
- **Janela:** 2026-10-14.
- **Foco:** impacto das suspensões na defesa.
- **Checagens:** lista oficial e alternativas prováveis.

### De la Cruz completa 100 jogos
- **Estado:** aprovada.
- **Janela:** 2026-10-14.
- **Foco:** avaliar custo-benefício.

## Pauta reservada para 15 de outubro de 2026

### Flamengo precisa aprender a matar jogos?
- **Estado:** reservada; confirmar se segue vigente.
- **Janela:** 2026-10-15.
- **Foco:** gestão de vantagem.
"""

RESERVAS = """# Projetos e Pautas Reservadas

## Projeto de reportagem sobre José Boto

### Flamengo recusou milhões para manter o elenco
- **Estado:** reservada para desenvolvimento posterior.
- **Objetivo:** estratégia de mercado.
- **Cuidados:** confirmar valores em fontes confiáveis.

## Pauta reservada para 15 de outubro de 2026

### Flamengo precisa aprender a matar jogos?
- **Estado:** reservada conforme registro de contexto.
- **Janela:** 2026-10-15.
- **Foco:** gestão de vantagem.
"""


def test_parse_pautas_reads_sections_fields_and_status() -> None:
    pautas = parse_pautas(PAINEL, "painel.md")

    assert [pauta.title for pauta in pautas] == [
        "Estudantes também tem problemas na defesa",
        "De la Cruz completa 100 jogos",
        "Flamengo precisa aprender a matar jogos?",
    ]
    assert [pauta.status for pauta in pautas] == [
        "indefinido",
        "aprovada",
        "reservada",
    ]
    assert [pauta.kind for pauta in pautas] == [
        "mencionada",
        "mencionada",
        "reservada",
    ]
    assert pautas[0].window == date(2026, 10, 14)
    assert pautas[1].window == date(2026, 10, 14)
    assert pautas[2].window == date(2026, 10, 15)
    assert pautas[0].fields["Foco"] == "impacto das suspensões na defesa."
    assert pautas[0].source == "painel.md"


def test_parse_pautas_keeps_pauta_without_window() -> None:
    content = """## Projetos

### Projeto sem data
- **Estado:** ideia.
- **Objetivo:** desenvolver depois.
"""
    pautas = parse_pautas(content, "reservas.md")

    assert len(pautas) == 1
    assert pautas[0].window is None
    assert pautas[0].kind == "projeto"
    assert pautas[0].status == "ideia"


def test_parse_pauta_documents_deduplicates_same_title_and_window() -> None:
    pautas = parse_pauta_documents({
        "painel.md": PAINEL,
        "reservas.md": RESERVAS,
    })

    titles = [pauta.title for pauta in pautas]
    assert titles.count("Flamengo precisa aprender a matar jogos?") == 1
    assert len(pautas) == 4
    assert pautas[-1].title == "Flamengo recusou milhões para manter o elenco"


def test_parse_pautas_ignores_headings_without_fields() -> None:
    content = """## Seção

### Título solto
Texto sem campos.

### Outro título
- **Estado:** em apuração.
"""
    pautas = parse_pautas(content, "nota.md")

    assert len(pautas) == 2
    assert pautas[0].status == "indefinido"
    assert pautas[1].status == "em_apuracao"
