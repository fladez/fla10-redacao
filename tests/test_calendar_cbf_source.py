from datetime import UTC, datetime
from fla10_agents.calendar.cbf_source import parse_cbf_table_text

PDF_URL = "https://cbf.com.br/tabela-detalhada.pdf"

def test_parse_cbf_table_extracts_only_flamengo_fixtures() -> None:
    text = """
368 37 29/11 dom 16:00 Coritiba PR x Flamengo RJ Couto Pereira Curitiba PR 1 7
369 37 29/11 dom 16:00 Vitória BA x Santos SP Barradão Salvador BA 1 6 7
371 38 02/12 qua 21:30 Flamengo RJ x Chapecoense SC Maracanã Rio de Janeiro RJ
"""
    events = parse_cbf_table_text(text, season=2026, source_url=PDF_URL, accessed_at=datetime(2026, 11, 10, 12, tzinfo=UTC))
    assert len(events) == 2
    away, away_id = events[0]
    home, home_id = events[1]
    assert away_id == "368"
    assert away.home_team == "Coritiba"
    assert away.away_team == "Flamengo"
    assert away.starts_at_local.isoformat() == "2026-11-29T16:00:00"
    assert home_id == "371"
    assert home.home_team == "Flamengo"
    assert home.away_team == "Chapecoense"
    assert home.stage == "rodada 38"
    assert home.sources[0].url == PDF_URL
