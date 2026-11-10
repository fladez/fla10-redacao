"""Ponte entre as versões exportadas pela redação CrewAI e o pacote de CMS.

Lê uma pasta de ``exports/redacao-*``, confere que a versão foi aprovada por
uma pessoa e monta o pacote reaproveitando a exportação de ``publication.py``.
Nada é enviado ao site.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import (
    DraftArticle,
    EditorialProposal,
    PublicationPackage,
    ReviewReport,
    SeoPackage,
)
from fla10_agents.publication import (
    PREPARED_STATUS,
    PUBLISHED_STATUS,
    PublicationError,
    export_package,
    slugify,
)
from fla10_agents.site_payload import pacote_do_site
from fla10_agents.writing.draft import render_site_html
from fla10_agents.writing.review import READY_VERDICT

MARCADOR_VERSAO = re.compile(r"<!--\s*VERSAO:(\d+)\s*-->", re.IGNORECASE)
MODELO_PADRAO = "opencode/deepseek-v4.1-flash-free"
FORMATO_PADRAO = "noticia"
MIN_CARACTERES_CORPO = 200
LIMITE_SUBTITULO = 220
LIMITE_META = 155
LIMITE_RESUMO = 480

PALAVRAS_VAZIAS = frozenset({
    "a", "as", "o", "os", "de", "do", "da", "dos", "das", "e", "em", "no", "na",
    "nos", "nas", "com", "para", "por", "um", "uma", "que", "mas", "ao", "aos",
    "se", "sobre", "como", "mais", "apos", "após",
})


class VersaoInvalida(PublicationError):
    """A pasta ou a versão pedida não tem texto utilizável."""


class VersaoNaoAprovada(PublicationError):
    """A versão não tem aprovação humana válida para este texto."""


def hash_versao(texto: str) -> str:
    """Impressão digital do texto exato que a pessoa aprovou."""
    return hashlib.sha256(texto.strip().encode("utf-8")).hexdigest()


def ler_versao(run_dir: str | Path, versao: int) -> str:
    """Lê ``versao-<n>.md``; sem o arquivo, divide ``completa.md`` pelo marcador."""
    pasta = Path(run_dir).expanduser()
    if not pasta.is_dir():
        raise VersaoInvalida(f"Pasta de execução não encontrada: {pasta}")

    arquivo = pasta / f"versao-{versao}.md"
    if arquivo.is_file():
        texto = arquivo.read_text(encoding="utf-8").strip()
        if not texto:
            raise VersaoInvalida(f"O arquivo {arquivo.name} está vazio.")
        return texto

    completa = pasta / "completa.md"
    if not completa.is_file():
        raise VersaoInvalida(
            f"Não há {arquivo.name} nem completa.md em {pasta.name}."
        )

    partes = MARCADOR_VERSAO.split(completa.read_text(encoding="utf-8"))
    for indice in range(1, len(partes), 2):
        if int(partes[indice]) == versao and partes[indice + 1].strip():
            return partes[indice + 1].strip()

    raise VersaoInvalida(f"A versão {versao} não existe em {pasta.name}.")


def ler_aprovacao(run_dir: str | Path, versao: int, texto: str) -> dict[str, Any]:
    """Confere ``aprovada.json``: mesma versão e mesmo texto aprovado."""
    pasta = Path(run_dir).expanduser()
    caminho = pasta / "aprovada.json"
    if not caminho.is_file():
        raise VersaoNaoAprovada(
            f"A versão {versao} de {pasta.name} não foi aprovada. "
            "Registre a aprovação na interface local antes de montar o pacote."
        )

    try:
        registro = json.loads(caminho.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise VersaoNaoAprovada(f"Registro de aprovação ilegível: {caminho.name}.") from exc

    if not isinstance(registro, dict) or int(registro.get("versao", 0)) != versao:
        raise VersaoNaoAprovada(
            f"O registro de aprovação de {pasta.name} não é da versão {versao}."
        )

    esperado = registro.get("conteudo_sha256")
    if isinstance(esperado, str) and esperado and esperado != hash_versao(texto):
        raise VersaoNaoAprovada(
            "O texto mudou depois da aprovação. Aprove novamente a versão atual."
        )

    return registro


def _blocos(markdown: str) -> list[str]:
    blocos: list[str] = []
    atual: list[str] = []
    for linha in markdown.splitlines():
        if linha.strip():
            atual.append(linha.strip())
        elif atual:
            blocos.append(" ".join(atual))
            atual = []
    if atual:
        blocos.append(" ".join(atual))
    return blocos


def _e_subtitulo(bloco: str) -> bool:
    if len(bloco) > LIMITE_SUBTITULO:
        return False
    return bool(
        re.fullmatch(r"\*\*[^*]+\*\*", bloco) or re.fullmatch(r"\*[^*]+\*", bloco)
    )


def _sem_marcacao(texto: str) -> str:
    return texto.replace("**", "").replace("*", "").strip()


def separar_artigo(markdown: str) -> tuple[str, str, str]:
    """Separa título, subtítulo opcional e corpo do Markdown da versão."""
    linhas = [linha.strip() for linha in markdown.splitlines()]
    titulo = ""
    inicio = 0
    for indice, linha in enumerate(linhas):
        if linha.startswith("# "):
            titulo = linha[2:].strip()
            inicio = indice + 1
            break

    if not titulo:
        raise VersaoInvalida("A versão não começa com um título '# '.")

    blocos = _blocos("\n".join(linhas[inicio:]))
    subtitulo = ""
    if blocos and _e_subtitulo(blocos[0]):
        subtitulo = _sem_marcacao(blocos[0])
        blocos = blocos[1:]

    corpo = "\n\n".join(blocos).strip()
    if len(corpo) < MIN_CARACTERES_CORPO:
        raise VersaoInvalida(
            f"O corpo da versão tem {len(corpo)} caracteres; "
            f"mínimo {MIN_CARACTERES_CORPO}."
        )

    return titulo, subtitulo, corpo


def _recortar(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return corte + "…"


def montar_resumo(corpo: str) -> str:
    """Usa o primeiro parágrafo como resumo autossuficiente."""
    primeiro = _sem_marcacao(corpo.split("\n\n", 1)[0])
    return _recortar(primeiro, LIMITE_RESUMO)


def montar_seo(titulo: str, resumo: str) -> SeoPackage:
    """SEO determinístico: nada é inventado, só derivado do texto aprovado."""
    palavras = [
        palavra.strip(".,:;!?()\"'")
        for palavra in titulo.split()
        if len(palavra) > 2
    ]
    secundarias: list[str] = []
    for palavra in palavras:
        limpa = palavra.lower()
        if limpa in PALAVRAS_VAZIAS or limpa in {"flamengo", "fla"}:
            continue
        if palavra[0].isupper() and palavra not in secundarias:
            secundarias.append(palavra)

    return SeoPackage(
        title=titulo,
        meta_description=_recortar(resumo, LIMITE_META),
        primary_keyword="Flamengo",
        secondary_keywords=secundarias[:5],
    )


def montar_posts(titulo: str, resumo: str) -> list[str]:
    """Textos curtos para redes, sem fato novo."""
    abertura = _recortar(resumo.split(". ", 1)[0].strip().rstrip("."), 200)
    return [
        f"{titulo}\n\n{abertura}.\n\n#Flamengo #FLA10News",
        f"{titulo} — a análise completa está no FLA10 News. 🔴⚫",
    ]


def _salvar_ou_reaproveitar(
    store: EditorialRepository,
    proposal: EditorialProposal,
    draft: DraftArticle,
    review: ReviewReport,
    package: PublicationPackage,
) -> None:
    if store.get_proposal(proposal.proposal_id) is None:
        store.save_proposal(proposal)

    existente = store.get_draft(draft.draft_id)
    if existente is None:
        store.save_draft(draft)
    elif existente.editorial_decision != "approved":
        store.decide_draft(draft.draft_id, "approved")

    if not any(item.review_id == review.review_id for item in store.list_reviews(draft.draft_id)):
        store.save_review(review)

    anterior = store.get_package(package.package_id)
    if anterior is not None and anterior.status == PUBLISHED_STATUS:
        raise PublicationError(
            f"O pacote {package.package_id} já foi registrado como publicado; "
            "importação bloqueada."
        )
    if anterior is None:
        store.save_package(package)
    else:
        store.update_package(package)


def importar_versao(
    run_dir: str | Path,
    versao: int,
    *,
    database_path: str | Path,
    output_root: str | Path,
    formato: str = FORMATO_PADRAO,
    now: datetime | None = None,
) -> tuple[PublicationPackage, Path]:
    """Monta e exporta o pacote de CMS de uma versão aprovada."""
    pasta = Path(run_dir).expanduser().resolve()
    texto = ler_versao(pasta, versao)
    registro = ler_aprovacao(pasta, versao, texto)

    titulo, subtitulo, corpo = separar_artigo(texto)
    referencia = now or datetime.now(UTC)
    identificador = f"{pasta.name}-v{versao}"
    resumo = montar_resumo(corpo)
    seo = montar_seo(titulo, resumo)
    html = render_site_html(corpo)
    pauta = str(registro.get("pauta") or "").strip()
    if not pauta:
        try:
            pauta = (pasta / "pauta.txt").read_text(encoding="utf-8").strip()
        except OSError:
            pauta = ""
    pauta = pauta or "pauta não registrada na aprovação"

    proposal = EditorialProposal(
        proposal_id=f"exports:{pasta.name}",
        title=titulo,
        format=formato,
        editorial_question=f"Versão {versao} aprovada para a pauta: {pauta}",
        angle="Versão da redação automatizada aprovada na interface local",
        why_now="Aprovação humana registrada em aprovada.json",
        editorial_decision="approved",
        created_at=referencia,
    )

    draft = DraftArticle(
        draft_id=identificador,
        proposal_id=f"exports:{pasta.name}",
        format=formato,
        title=titulo,
        subtitle=subtitulo,
        body_markdown=corpo,
        body_html=html,
        ai_summary=resumo,
        seo=seo,
        social_posts=montar_posts(titulo, resumo),
        sources=[],
        model=MODELO_PADRAO,
        prompt_version="exports-v1",
        generation={
            "origem": str(pasta),
            "versao": versao,
            "aprovada_em": registro.get("aprovada_em"),
            "conteudo_sha256": hash_versao(texto),
        },
        editorial_decision="approved",
        created_at=referencia,
    )

    review = ReviewReport(
        review_id=f"{identificador}-aprovacao",
        draft_id=identificador,
        verdict=READY_VERDICT,
        issues=[],
        checks=["aprovacao humana registrada em aprovada.json"],
        summary="Versão aprovada manualmente na interface local.",
        reviewer_model="aprovacao-humana",
        reviewed_at=referencia,
    )

    with EditorialRepository(database_path) as store:
        anterior = store.get_package(identificador)
        pacote = PublicationPackage(
            package_id=identificador,
            draft_id=identificador,
            format=formato,
            title=titulo,
            subtitle=subtitulo,
            slug=slugify(titulo),
            body_html=html,
            body_markdown=corpo,
            ai_summary=resumo,
            seo=seo,
            social_posts=draft.social_posts,
            sources=[],
            status=PREPARED_STATUS,
            created_at=anterior.created_at if anterior is not None else referencia,
        )
        _salvar_ou_reaproveitar(store, proposal, draft, review, pacote)

    destino = export_package(database_path, identificador, output_root, now=referencia)

    with EditorialRepository(database_path) as store:
        exportado = store.get_package(identificador) or pacote

    (destino / "site-news.json").write_text(
        json.dumps(pacote_do_site(exportado), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return exportado, destino
