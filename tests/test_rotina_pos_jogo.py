"""Testes da rotina pós-jogo, sem chamar o pipeline."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rotina_pos_jogo
from rotina_pos_jogo import decidir, pauta_do_jogo

FUSO = ZoneInfo("America/Sao_Paulo")
JOGO = {
    "rodada": 34,
    "quando": "04/11/2026 19:30",
    "mandante": "Flamengo",
    "visitante": "Grêmio",
    "gols_mandante": 3,
    "gols_visitante": 1,
    "estadio": "Maracanã",
    "detalhes": [],
}


def test_jogo_recente_manda_executar() -> None:
    decisao = decidir(JOGO, datetime(2026, 11, 4, 22, 0, tzinfo=FUSO))

    assert decisao["status"] == "executar"
    assert decisao["placar"] == "Flamengo 3 x 1 Grêmio"
    assert "Grêmio" in decisao["pauta"]
    assert "declarações" in decisao["pauta"]


def test_jogo_antigo_nao_roda() -> None:
    decisao = decidir(JOGO, datetime(2026, 11, 5, 12, 0, tzinfo=FUSO))

    assert decisao["status"] == "sem_jogo_recente"
    assert decisao["idade_horas"] > rotina_pos_jogo.JANELA_HORAS


def test_jogo_ja_redigido_nao_repete() -> None:
    anterior = {"rodada": 34, "quando": "04/11/2026 19:30", "pasta": "redacao-x"}

    decisao = decidir(JOGO, datetime(2026, 11, 4, 23, 40, tzinfo=FUSO), anterior)

    assert decisao["status"] == "ja_gerado"
    assert decisao["pasta"] == "redacao-x"


def test_marcador_de_outro_jogo_libera_nova_rodada() -> None:
    anterior = {"rodada": 33, "quando": "28/10/2026 19:30", "pasta": "redacao-y"}

    decisao = decidir(JOGO, datetime(2026, 11, 4, 23, 40, tzinfo=FUSO), anterior)

    assert decisao["status"] == "executar"


def test_pauta_do_jogo_cita_os_dois_times() -> None:
    pauta = pauta_do_jogo(JOGO)

    assert pauta.startswith("Flamengo 3 x 1 Grêmio")
    assert "resultado" in pauta


def test_cli_sem_executar_nao_chama_pipeline(tmp_path, monkeypatch, capsys) -> None:
    recente = datetime.now(FUSO) - timedelta(hours=2)
    jogo = {**JOGO, "quando": recente.strftime("%d/%m/%Y %H:%M")}
    monkeypatch.setattr(rotina_pos_jogo, "MARCADOR", tmp_path / "marcador.json")
    monkeypatch.setattr(rotina_pos_jogo, "coletar_jogo", lambda: (jogo, ""))
    monkeypatch.setattr("sys.argv", ["rotina_pos_jogo.py", "--sem-executar"])

    with pytest.raises(SystemExit) as fim:
        rotina_pos_jogo.main()

    assert fim.value.code == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "executar"
    assert not (tmp_path / "marcador.json").exists()


def test_cli_sem_dados_falha(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(rotina_pos_jogo, "MARCADOR", tmp_path / "marcador.json")
    monkeypatch.setattr(rotina_pos_jogo, "coletar_jogo", lambda: (None, "fonte fora do ar"))
    monkeypatch.setattr("sys.argv", ["rotina_pos_jogo.py"])

    with pytest.raises(SystemExit) as fim:
        rotina_pos_jogo.main()

    assert fim.value.code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "sem_dados"
    assert "fonte fora do ar" in payload["erro"]
