from datetime import date

from fla10_agents.editorial.pautas import Pauta
from fla10_agents.editorial.redundancy import check_redundancy, tokenize


def make_pauta(title: str, focus: str = "") -> Pauta:
    fields = {"Foco": focus} if focus else {}
    return Pauta(
        title=title,
        status="reservada",
        kind="reservada",
        window=date(2026, 10, 15),
        fields=fields,
        source="06 - Pautas/Painel de Pautas.md",
    )


def test_tokenize_removes_accents_stopwords_and_short_terms() -> None:
    terms = tokenize("O Flamengo não vai jogar em São Paulo")

    assert "flamengo" in terms
    assert "jogar" in terms
    assert "paulo" in terms
    assert "nao" not in terms
    assert "sao" not in terms
    assert "vai" not in terms


def test_title_match_against_published_article_is_high_risk() -> None:
    report = check_redundancy(
        "Flamengo x Palmeiras: onde assistir, horário e o que esperar",
        "Serviço de jogo com transmissão e estádio.",
        published=["Flamengo x Palmeiras: onde assistir"],
    )

    assert report.risk == "alto"
    assert report.score >= 0.55
    assert report.related_titles == ["Flamengo x Palmeiras: onde assistir"]


def test_title_match_against_reserved_pauta_is_high_risk() -> None:
    pauta = make_pauta(
        "Flamengo precisa aprender a matar jogos?",
        "gestão de vantagem em partidas recentes",
    )

    report = check_redundancy(
        "Flamengo precisa aprender a matar jogos?",
        "comparar partidas para avaliar controle de vantagem",
        pautas=[pauta],
    )

    assert report.risk == "alto"
    assert report.related_titles == [pauta.title]


def test_unrelated_topic_is_low_risk() -> None:
    report = check_redundancy(
        "Previsão do tempo no Rio de Janeiro",
        "Meteorologia e temperatura.",
        pautas=[make_pauta("Flamengo precisa aprender a matar jogos?")],
        published=["Flamengo x Palmeiras: onde assistir"],
    )

    assert report.risk == "baixo"
    assert report.matches == ()


def test_medium_overlap_is_classified_as_medium() -> None:
    pauta = make_pauta(
        "Flamengo e Palmeiras decidem vaga na semifinal",
        "jogo decisivo no Maracanã",
    )

    report = check_redundancy(
        "Palmeiras enfrenta o Flamengo em jogo decisivo",
        "análise do confronto",
        pautas=[pauta],
    )

    assert report.risk in ("medio", "alto")
    assert report.score >= 0.35


def test_context_can_lift_score_beyond_title_only() -> None:
    pauta = make_pauta("Análise do elenco", "suspensões e desfalques confirmados")

    report = check_redundancy(
        "Boletim médico do Flamengo",
        "suspensões e desfalques confirmados para o próximo jogo",
        pautas=[pauta],
    )

    assert report.score >= 0.3
