"""Testes da ponte entre versões aprovadas em exports/ e o pacote de CMS."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fla10_agents import site_payload
from fla10_agents.cli import main
from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.publication import PublicationError
from fla10_agents.publication_import import (
    VersaoInvalida,
    VersaoNaoAprovada,
    hash_versao,
    importar_versao,
    ler_versao,
    separar_artigo,
)

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)

CORPO = (
    "A Confederação Brasileira de Futebol confirmou a final da Copa do Brasil "
    "Feminina no Estádio Luso-Brasileiro, na Ilha do Governador. A decisão foi "
    "registrada pelo ge e repercutida pela imprensa carioca ao longo do dia. "
    "O Flamengo enfrenta o Internacional em busca do título inédito da competição, "
    "e a torcida organiza caravana para acompanhar a partida de perto."
)

VERSAO = f"""# Flamengo decide a Copa do Brasil Feminina no Luso-Brasileiro

**A CBF confirmou o estádio da final e encerrou a pressão por um jogo no Maracanã.**

{CORPO}

## O que muda para a Nação

A mudança de palco altera o planejamento de quem vai ao jogo e o esquema de viagem.
"""


def escrever_execucao(tmp_path: Path, versao: int = 1, *, texto: str = VERSAO,
                      aprovada: bool = True) -> Path:
    pasta = tmp_path / "exports" / "redacao-2026-11-10-1622"
    pasta.mkdir(parents=True)
    (pasta / "completa.md").write_text(f"<!-- VERSAO:{versao} -->\n{texto}\n", encoding="utf-8")
    (pasta / f"versao-{versao}.md").write_text(texto + "\n", encoding="utf-8")
    if aprovada:
        (pasta / "aprovada.json").write_text(
            json.dumps(
                {
                    "pasta": pasta.name,
                    "versao": versao,
                    "aprovada_em": "2026-11-10T18:00:00",
                    "conteudo_sha256": hash_versao(texto),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return pasta


def importar(tmp_path: Path, pasta: Path, versao: int = 1):
    return importar_versao(
        pasta,
        versao,
        database_path=tmp_path / "editorial.db",
        output_root=tmp_path / "pacotes",
        now=NOW,
    )


def test_separar_artigo_extrai_titulo_subtitulo_e_corpo() -> None:
    titulo, subtitulo, corpo = separar_artigo(VERSAO)

    assert titulo == "Flamengo decide a Copa do Brasil Feminina no Luso-Brasileiro"
    assert subtitulo.startswith("A CBF confirmou o estádio da final")
    assert corpo.startswith("A Confederação Brasileira de Futebol")
    assert "## O que muda para a Nação" in corpo
    assert "**A CBF" not in corpo


def test_separar_artigo_aceita_titulo_com_dois_cerquilhas() -> None:
    texto = f"## Título de nível dois\n\n{CORPO}\n"

    titulo, subtitulo, corpo = separar_artigo(texto)

    assert titulo == "Título de nível dois"
    assert subtitulo == ""
    assert corpo.startswith("A Confederação")


def test_separar_artigo_sem_subtitulo_mantem_lead() -> None:
    texto = f"# Título direto\n\n{CORPO}\n"

    titulo, subtitulo, corpo = separar_artigo(texto)

    assert titulo == "Título direto"
    assert subtitulo == ""
    assert corpo.startswith("A Confederação")


def test_separar_artigo_sem_titulo_falha() -> None:
    with pytest.raises(VersaoInvalida):
        separar_artigo(f"Texto solto\n\n{CORPO}")


def test_separar_artigo_com_corpo_curto_falha() -> None:
    with pytest.raises(VersaoInvalida):
        separar_artigo("# Título\n\nCurto demais.")


def test_ler_versao_cai_para_completa_quando_falta_arquivo(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)
    (pasta / "versao-1.md").unlink()

    assert ler_versao(pasta, 1).startswith("# Flamengo decide")


def test_ler_versao_inexistente_falha(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)

    with pytest.raises(VersaoInvalida):
        ler_versao(pasta, 3)


def test_importar_exige_aprovacao_humana(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path, aprovada=False)

    with pytest.raises(VersaoNaoAprovada):
        importar(tmp_path, pasta)


def test_importar_rejeita_aprovacao_de_outra_versao(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)
    (pasta / "aprovada.json").write_text(
        json.dumps({"versao": 2, "conteudo_sha256": hash_versao(VERSAO)}),
        encoding="utf-8",
    )

    with pytest.raises(VersaoNaoAprovada):
        importar(tmp_path, pasta)


def test_importar_rejeita_texto_alterado_depois_da_aprovacao(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)
    (pasta / "versao-1.md").write_text(VERSAO.replace("Luso", "Maracanã") + "\n",
                                       encoding="utf-8")

    with pytest.raises(VersaoNaoAprovada):
        importar(tmp_path, pasta)


def test_importar_monta_pacote_exportado(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)

    pacote, destino = importar(tmp_path, pasta)

    assert pacote.status == "exported"
    assert pacote.title == "Flamengo decide a Copa do Brasil Feminina no Luso-Brasileiro"
    assert pacote.slug == "flamengo-decide-a-copa-do-brasil-feminina-no-luso-brasileiro"
    assert pacote.draft_id == "redacao-2026-11-10-1622-v1"
    assert pacote.seo.primary_keyword == "Flamengo"
    assert len(pacote.social_posts) == 2
    assert destino == tmp_path / "pacotes" / "redacao-2026-11-10-1622-v1"
    for arquivo in ("article.html", "article.md", "package.json", "metadata.json"):
        assert (destino / arquivo).is_file()

    markdown = (destino / "article.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Flamengo decide")
    assert "## A CBF confirmou o estádio da final" in markdown
    assert "<h3>O que muda para a Nação</h3>" in (destino / "article.html").read_text(
        encoding="utf-8"
    )


def test_pacote_sem_subtitulo_nao_gera_titulo_vazio(tmp_path) -> None:
    texto = f"# Título direto\n\n{CORPO}\n"
    pasta = escrever_execucao(tmp_path, texto=texto)

    _, destino = importar(tmp_path, pasta)

    markdown = (destino / "article.md").read_text(encoding="utf-8")
    assert "## \n" not in markdown
    assert markdown.startswith("# Título direto\n\nA Confederação")


def test_importar_duas_vezes_nao_duplica_registros(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)

    importar(tmp_path, pasta)
    importar(tmp_path, pasta)

    with EditorialRepository(tmp_path / "editorial.db") as store:
        assert len(store.list_packages()) == 1
        assert len(store.list_drafts()) == 1
        assert len(store.list_reviews("redacao-2026-11-10-1622-v1")) == 1


def test_reimportar_pacote_publicado_e_bloqueado(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)
    pacote, _ = importar(tmp_path, pasta)
    publicado = pacote.model_copy(update={"status": "published"})
    with EditorialRepository(tmp_path / "editorial.db") as store:
        store.update_package(publicado)

    with pytest.raises(PublicationError):
        importar(tmp_path, pasta)


def test_importar_gera_documento_no_formato_do_site(tmp_path) -> None:
    pasta = escrever_execucao(tmp_path)

    _, destino = importar(tmp_path, pasta)

    dados = json.loads((destino / "site-news.json").read_text(encoding="utf-8"))
    documento = dados["documento"]
    assert documento["status"] == "draft"
    assert documento["mainCategory"] == "Futebol"
    assert documento["category"] == "Feminino"
    assert documento["title"].startswith("Flamengo decide")
    assert documento["excerpt"].startswith("A CBF confirmou")
    assert documento["content"].startswith("A Confederação")
    assert documento["focusKeyword"] == "Flamengo"
    assert documento["secondaryKeywords"] == "Copa, Brasil, Feminina, Luso-Brasileiro"
    assert documento["image"] == ""
    assert dados["destino"].startswith("coleção news")
    assert any("imagem" in pendencia.lower() for pendencia in dados["pendencias"])


def test_subcategoria_reconhece_base_e_profissional() -> None:
    assert site_payload.subcategoria("Flamengo vence o clássico", "jogo do time principal") == (
        "Profissional"
    )
    assert site_payload.subcategoria("Sub-20 goleia no Brasileirão", "") == "Base"
    assert site_payload.subcategoria("Final feminina no Luso", "") == "Feminino"


def test_cli_importar_imprime_pacote(tmp_path, monkeypatch, capsys) -> None:
    pasta = escrever_execucao(tmp_path)
    banco = tmp_path / "editorial.db"
    saida = tmp_path / "pacotes"

    monkeypatch.setattr(
        "sys.argv",
        [
            "fla10",
            "publicacao",
            "importar",
            str(pasta),
            "--versao",
            "1",
            "--output",
            str(saida),
            "--database",
            str(banco),
        ],
    )
    with pytest.raises(SystemExit) as fim:
        main()

    assert fim.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "exported"
    assert payload["files"] == [
        "article.html",
        "article.md",
        "package.json",
        "metadata.json",
        "site-news.json",
    ]
    assert Path(payload["output"]).is_dir()
