"""Testes da verificação determinística das versões."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import qualidade

TEXTO = " ".join(["Flamengo vence o Grêmio com dois gols de Pedro no Maracanã."] * 12)
VERSAO = f"# Título da versão\n\n{TEXTO}\n"


def versoes_completas() -> list[tuple[int, str]]:
    return [(numero, f"{VERSAO}\nMarca da versão {numero}.") for numero in range(1, 5)]


def test_quatro_versoes_validas_nao_geram_aviso() -> None:
    assert qualidade.avaliar(versoes_completas()) == []
    assert qualidade.pode_aprovar([])


def test_quantidade_diferente_apenas_avisa() -> None:
    avisos = qualidade.avaliar(versoes_completas()[:3])

    assert any("esperava 4" in aviso.mensagem for aviso in avisos)
    assert qualidade.pode_aprovar(avisos)


def test_versao_sem_titulo_e_erro() -> None:
    avisos = qualidade.avaliar([(1, TEXTO)])

    assert any(aviso.critico and aviso.versao == 1 for aviso in avisos)


def test_texto_curto_apenas_avisa() -> None:
    avisos = qualidade.avaliar([(1, "# Título\n\nCurto.")])

    assert any(aviso.nivel == "atencao" and "texto curto" in aviso.mensagem for aviso in avisos)
    assert qualidade.pode_aprovar(avisos)


def test_marcador_vazado_e_erro() -> None:
    avisos = qualidade.avaliar([(1, "# Título\n\n<!-- VERSAO:2 -->\n" + TEXTO)])

    assert any(aviso.critico and "marcador" in aviso.mensagem for aviso in avisos)


def test_negrito_nao_fechado_avisa() -> None:
    avisos = qualidade.avaliar([(1, f"# Título\n\n**{TEXTO}")])

    assert any("negrito" in aviso.mensagem for aviso in avisos)


def test_nao_encontrado_avisa() -> None:
    avisos = qualidade.avaliar([(1, f"# Título\n\n{TEXTO} O placar não encontrado.")])

    assert any("não encontrado" in aviso.mensagem for aviso in avisos)


def test_versoes_quase_iguais_avisam() -> None:
    iguais = [(1, VERSAO), (2, VERSAO + "\n")]

    avisos = qualidade.avaliar(iguais)

    assert any("quase iguais" in aviso.mensagem for aviso in avisos)


def test_similaridade_de_textos_diferentes_e_baixa() -> None:
    a = "Flamengo vence o Grêmio no Maracanã com gols de Pedro e Samuel Lino."
    b = "A CBF confirmou a final feminina no estádio Luso-Brasileiro, na Ilha."

    assert qualidade.similaridade(a, b) < 0.3
    assert qualidade.similaridade(a, a) == 1.0


def test_titulo_de_nivel_dois_e_aceito() -> None:
    versoes = [(1, f"## Título de nível dois\n\n{TEXTO}")]

    avisos = qualidade.avaliar(versoes)

    assert not any("título" in aviso.mensagem for aviso in avisos)


def test_varios_dados_ausentes_avisam() -> None:
    texto = (
        f"# Título\n\n{TEXTO} O placar não foi divulgado. "
        "A escalação não foi informada."
    )

    avisos = qualidade.avaliar([(1, texto)])

    assert any("dado ausente" in aviso.mensagem for aviso in avisos)
    assert qualidade.pode_aprovar(avisos)


def test_um_dado_ausente_nao_avisa() -> None:
    texto = f"# Título\n\n{TEXTO} O placar não foi divulgado."

    avisos = qualidade.avaliar([(1, texto)])

    assert not any("dado ausente" in aviso.mensagem for aviso in avisos)
