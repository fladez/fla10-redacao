"""Painel do fluxo editorial: proposta → dossiê → minuta → revisão → decisão.

Toda etapa chama a CLI (`python -m fla10_agents`) porque o pacote vive no
`.venv`, e não no ambiente do Streamlit. Nenhuma etapa publica no site.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

ETAPAS = ("1. Propostas", "2. Dossiê", "3. Minuta", "4. Revisão", "5. Decisão")
TEMPO_GERACAO = "cerca de 1 a 2 minutos"

MODELO_CLAIMS: dict[str, Any] = {
    "claims": [
        {
            "claim_id": "c1",
            "claim_text": "Substitua pelo fato apurado.",
            "classification": "confirmed",
            "evidence": [
                {
                    "url": "https://exemplo.com/fonte",
                    "source_type": "site oficial",
                    "author_or_institution": "Nome da instituição",
                    "accessed_at": "",
                    "supports": ["o que esta fonte sustenta"],
                }
            ],
        }
    ]
}

# Valores que o painel troca pelo horário do clique.
ACCESS_PLACEHOLDERS = frozenset({"", "PREENCHER", "AGORA", "AUTO"})


def modelo_claims_json() -> str:
    """Modelo de afirmações para download, com accessed_at em branco."""
    return json.dumps(MODELO_CLAIMS, ensure_ascii=False, indent=2)


def _json_de_texto(texto: str) -> Any:
    try:
        return json.loads(texto)
    except ValueError as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc


def preparar_claims(payload: Any, *, agora: datetime | None = None) -> dict[str, Any]:
    """Confere o formato mínimo e preenche accessed_at no envio.

    A validação completa continua na CLI. Aqui só evitamos gravar um dossiê
    com data de acesso vazia, que o schema recusaria.
    """
    momento = agora or datetime.now(UTC)

    if isinstance(payload, dict):
        itens = payload.get("claims")
        if not isinstance(itens, list):
            raise TypeError("O JSON precisa ter a lista 'claims'.")
        normalizado = dict(payload)
    elif isinstance(payload, list):
        itens = payload
        normalizado = {"claims": itens}
    else:
        raise TypeError("Envie uma lista de afirmações ou um objeto com 'claims'.")

    for indice, item in enumerate(itens, start=1):
        if not isinstance(item, dict):
            raise TypeError(f"Afirmação {indice}: esperado um objeto JSON.")
        evidencias = item.get("evidence") or []
        if not isinstance(evidencias, list):
            raise TypeError(f"Afirmação {indice}: 'evidence' deve ser uma lista.")
        for evidencia in evidencias:
            if not isinstance(evidencia, dict):
                raise TypeError(f"Afirmação {indice}: evidência deve ser um objeto.")
            valor = str(evidencia.get("accessed_at") or "").strip()
            if valor.upper() in ACCESS_PLACEHOLDERS:
                evidencia["accessed_at"] = momento.isoformat()

    return normalizado



def _cli(
    python: Path,
    base: Path,
    *args: str,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    """Roda um comando da CLI e devolve o processo, sem publicar nada."""
    try:
        return subprocess.run(
            [str(python), "-m", "fla10_agents", *args],
            cwd=base,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args, -1, "", f"O comando passou de {timeout} s e foi interrompido."
        )


def _json(processo: subprocess.CompletedProcess[str]) -> Any:
    try:
        return json.loads(processo.stdout)
    except ValueError:
        return None


def _erro(processo: subprocess.CompletedProcess[str], acao: str) -> None:
    """Mostra a falha da CLI com a saída útil, sem vazar caminho de segredo."""
    detalhe = (processo.stderr or processo.stdout or "").strip()
    st.error(f"{acao} falhou (código {processo.returncode}).")
    if detalhe:
        st.code(detalhe[-4000:])


def _aviso(texto: str, tipo: str = "success") -> None:
    st.session_state["painel-aviso"] = (tipo, texto)


def _mostrar_aviso() -> None:
    aviso = st.session_state.pop("painel-aviso", None)
    if not aviso:
        return
    tipo, texto = aviso
    getattr(st, tipo, st.info)(texto)


def _valores(processo: subprocess.CompletedProcess[str], acao: str) -> Any:
    """JSON esperado; em falha mostra o erro e devolve None."""
    if processo.returncode != 0:
        _erro(processo, acao)
        return None
    return _json(processo)


FORMATOS_LEGIVEIS = {
    "onde_assistir": "Onde assistir",
    "ultimas_noticias": "Últimas notícias",
}


def _formato_legivel(nome: str) -> str:
    return FORMATOS_LEGIVEIS.get(nome, nome)


def _data_curta(valor: str | None) -> str:
    """`2026-11-29` → `29/11/2026`; devolve o original se não for ISO."""
    if not valor:
        return "—"
    partes = valor.split("-")
    if len(partes) == 3 and all(parte.isdigit() for parte in partes):
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return valor


def _corpo_dossie(dossie: dict[str, Any]) -> None:
    recomendacao = dossie.get("recommendation", "")
    if recomendacao == "pronto para redação":
        st.success(f"Recomendação: **{recomendacao}**")
    else:
        st.warning(f"Recomendação: **{recomendacao}**")

    fatos = dossie.get("usable_facts") or []
    lacunas = dossie.get("gaps") or []
    contradicoes = dossie.get("contradictions") or []
    atribuicao = dossie.get("attribution_required") or []
    excluidas = dossie.get("excluded_claims") or []

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown(f"**Fatos utilizáveis ({len(fatos)})**")
        if fatos:
            for fato in fatos:
                st.markdown(f"- {fato}")
        else:
            st.caption("Nenhum fato confirmado com evidência.")
    with direita:
        st.markdown(f"**Lacunas declaradas ({len(lacunas)})**")
        if lacunas:
            for lacuna in lacunas:
                st.markdown(f"- {lacuna}")
        else:
            st.caption("Nenhuma lacuna registrada.")

    if contradicoes:
        st.error("Contradições: " + "; ".join(contradicoes))
    if atribuicao:
        with st.expander(f"Exige atribuição ({len(atribuicao)})"):
            for item in atribuicao:
                st.markdown(f"- {item}")
    if excluidas:
        with st.expander(f"Afirmações excluídas ({len(excluidas)})"):
            for item in excluidas:
                st.markdown(f"- {item}")

    with st.expander("Ver afirmações e fontes"):
        for claim in dossie.get("claims") or []:
            st.markdown(
                f"**{claim.get('claim_text')}**  \n"
                f"classificação: `{claim.get('classification')}`"
            )
            for evidencia in claim.get("evidence") or []:
                st.caption(
                    f"{evidencia.get('source_type')} · "
                    f"{evidencia.get('author_or_institution') or 'autoria não informada'} · "
                    f"{evidencia.get('url')}"
                )


def _corpo_minuta(rascunho: dict[str, Any]) -> None:
    abas = st.tabs(["Corpo", "SEO", "Redes", "Fontes", "Ficha técnica"])

    with abas[0]:
        st.markdown(rascunho.get("body_markdown", ""))
        st.download_button(
            "Baixar Markdown",
            rascunho.get("body_markdown", ""),
            file_name=f"{rascunho.get('draft_id', 'minuta')[:8]}.md",
            key=f"baixar-minuta-{rascunho.get('draft_id')}",
        )

    with abas[1]:
        seo = rascunho.get("seo") or {}
        st.markdown(f"**Título SEO:** {seo.get('title', '')}")
        st.markdown(f"**Descrição:** {seo.get('meta_description', '')}")
        st.markdown(f"**Palavra-chave:** {seo.get('primary_keyword', '')}")
        secundarias = seo.get("secondary_keywords") or []
        if secundarias:
            st.markdown("**Secundárias:** " + ", ".join(secundarias))
        if rascunho.get("ai_summary"):
            st.markdown("**Resumo para IA:**")
            st.write(rascunho["ai_summary"])

    with abas[2]:
        posts = rascunho.get("social_posts") or []
        if not posts:
            st.caption("Nenhum texto social gerado.")
        for indice, post in enumerate(posts, start=1):
            st.text_area(
                f"Post {indice}",
                post,
                height=110,
                key=f"social-{rascunho.get('draft_id')}-{indice}",
            )

    with abas[3]:
        fontes = rascunho.get("sources") or []
        if not fontes:
            st.caption("Nenhuma fonte registrada.")
        for fonte in fontes:
            st.markdown(
                f"- **{fonte.get('source_type')}** · "
                f"{fonte.get('author_or_institution') or 'autoria não informada'}"
            )
            st.caption(str(fonte.get("url", "")))

    with abas[4]:
        geracao = rascunho.get("generation") or {}
        uso = geracao.get("usage") or {}
        st.markdown(
            f"- **Modelo:** `{rascunho.get('model', '')}`\n"
            f"- **Servido como:** `{geracao.get('served_model', 'não informado')}`\n"
            f"- **Tokens:** {uso.get('prompt_tokens', '?')} de entrada + "
            f"{uso.get('completion_tokens', '?')} de saída\n"
            f"- **Custo:** {uso.get('cost', '?')}\n"
            f"- **Tempo:** {geracao.get('elapsed_seconds', '?')} s\n"
            f"- **Vault:** `{str(geracao.get('vault_commit', 'não informado'))[:12]}`\n"
            f"- **Prompt:** `{rascunho.get('prompt_version', '')}`"
        )
        documentos = geracao.get("documents") or []
        if documentos:
            with st.expander(f"Documentos editoriais usados ({len(documentos)})"):
                for documento in documentos:
                    st.markdown(f"- `{documento}`")


def _corpo_revisao(revisao: dict[str, Any] | None) -> None:
    if not revisao:
        st.caption("Nenhuma revisão registrada para esta minuta.")
        return

    veredito = revisao.get("verdict", "")
    resumo = revisao.get("summary") or ""

    if veredito == "pronto_para_avaliacao_humana":
        st.success(f"Veredito: **{veredito}**")
    elif veredito == "bloqueado":
        st.error(f"Veredito: **{veredito}**")
    else:
        st.warning(f"Veredito: **{veredito}**")

    st.caption(f"Revisor: `{revisao.get('reviewer_model', 'não informado')}`")
    if resumo:
        st.write(resumo)

    problemas = revisao.get("issues") or []
    if not problemas:
        st.caption("Nenhum problema apontado.")
        return

    st.markdown(f"**Problemas ({len(problemas)})**")
    for problema in problemas:
        severidade = problema.get("severity", "")
        marca = {"critico": "❌", "alto": "🟠", "medio": "⚠️", "baixo": "·"}.get(
            severidade, "·"
        )
        with st.expander(
            f"{marca} {severidade} · {problema.get('category', '')}", expanded=False
        ):
            st.write(problema.get("description", ""))
            if problema.get("evidence"):
                st.caption(problema["evidence"])


def render(
    python: Path,
    base: Path,
    banco: Path,
    calendario: Path,
) -> None:
    """Desenha o fluxo completo de pautas e minutas."""
    st.header("Pautas e minutas")
    st.caption(
        "Pesquisa de pauta, dossiê e minuta com decisão humana. "
        "Nenhuma etapa publica no portal."
    )
    _mostrar_aviso()

    st.markdown(" → ".join(ETAPAS))

    # --- 1. Propostas --------------------------------------------------
    st.subheader(ETAPAS[0])
    with st.expander("Gerar propostas a partir da agenda e do vault"):
        st.caption(
            "Lê a agenda de jogos e as pautas do vault. Cria proposta para "
            "jogo do Flamengo dentro da janela e para pauta pendente do vault; "
            "pauta encerrada ou vencida fica fora."
        )
        dias = st.number_input(
            "Janela de jogos (dias)",
            min_value=1,
            max_value=180,
            value=7,
            key="painel-dias",
        )
        if st.button("Gerar propostas", key="painel-gerar-propostas"):
            with st.spinner("Lendo agenda e vault..."):
                processo = _cli(
                    python,
                    base,
                    "pipeline",
                    "run",
                    "--event-days",
                    str(int(dias)),
                    "--database",
                    str(banco),
                    "--calendar-database",
                    str(calendario),
                )
            resultado = _valores(processo, "Gerar propostas")
            if resultado is not None:
                criadas = resultado.get("created", 0)
                _aviso(
                    f"{criadas} proposta(s) criada(s); "
                    f"{resultado.get('skipped', 0)} já existiam. "
                    f"Eventos na janela: {resultado.get('events', 0)}."
                )
                st.rerun()

    filtro = st.selectbox(
        "Filtrar propostas",
        options=["todas", "awaiting_human", "approved", "rejected"],
        key="painel-filtro",
    )
    argumentos = ["pautas", "list", "--database", str(banco)]
    if filtro != "todas":
        argumentos += ["--status", filtro]
    propostas = _valores(_cli(python, base, *argumentos), "Listar propostas") or []

    if not propostas:
        st.info(
            "Nenhuma proposta registrada. Gere a partir da agenda acima — ou "
            "amplie a janela de jogos, se o próximo jogo estiver longe."
        )
        return

    por_id = {proposta["proposal_id"]: proposta for proposta in propostas}
    escolhida_id = st.selectbox(
        "Proposta",
        options=list(por_id),
        format_func=lambda chave: (
            f"{por_id[chave]['title']} · "
            f"{_formato_legivel(str(por_id[chave]['format']))} · "
            f"{por_id[chave]['decision']}"
        ),
        key="painel-proposta",
    )
    proposta = por_id[escolhida_id]

    st.markdown(
        f"**Formato:** {_formato_legivel(str(proposta.get('format') or '—'))} · "
        f"**Janela:** {_data_curta(proposta.get('window'))} · "
        f"**Prioridade:** {proposta.get('priority') or '—'} · "
        f"**Redundância:** {proposta.get('redundancy_risk') or '—'} · "
        f"**Decisão:** {proposta.get('decision') or '—'}"
    )

    if proposta.get("related_published"):
        st.warning(
            "Tema já publicado: " + ", ".join(proposta["related_published"])
        )

    decisao = proposta.get("decision")
    if decisao != "approved":
        st.caption(
            "A pauta precisa estar aprovada antes do dossiê. "
            "Aprovar aqui só registra a decisão editorial."
        )
        col_a, col_b = st.columns(2)
        if col_a.button("Aprovar pauta", key="painel-aprovar-pauta", type="primary"):
            processo = _cli(
                python, base, "pautas", "approve", escolhida_id,
                "--database", str(banco),
            )
            if _valores(processo, "Aprovar pauta") is not None:
                _aviso("Pauta aprovada para apuração.")
                st.rerun()
        if col_b.button("Rejeitar pauta", key="painel-rejeitar-pauta"):
            processo = _cli(
                python, base, "pautas", "reject", escolhida_id,
                "--database", str(banco),
            )
            if _valores(processo, "Rejeitar pauta") is not None:
                _aviso("Pauta rejeitada.", "warning")
                st.rerun()

    # --- 2. Dossiê -----------------------------------------------------
    st.subheader(ETAPAS[1])
    dossie = _valores(
        _cli(python, base, "dossie", "mostrar", escolhida_id, "--database", str(banco)),
        "Ler dossiê",
    )

    if dossie:
        _corpo_dossie(dossie)
        rotulo = "Refazer dossiê"
    else:
        st.caption(
            "O dossiê reúne os fatos confirmados da pauta com a fonte de cada um "
            "e declara o que ainda falta. Não inventa dado."
        )
        rotulo = "Montar dossiê"

    with st.expander("Afirmações e fontes (opcional)"):
        st.caption(
            "Cole ou envie as afirmações apuradas, cada uma com a fonte. Sem "
            "isso, o dossiê fica só com as checagens da pauta e tende a não "
            "chegar a 'pronto para redação'."
        )
        st.download_button(
            "Baixar modelo JSON",
            modelo_claims_json(),
            file_name="afirmacoes-modelo.json",
            mime="application/json",
            key="painel-modelo-claims",
        )
        afirmacoes_texto = st.text_area(
            "Afirmações (JSON)",
            height=220,
            placeholder='{"claims": [{"claim_id": "c1", ...}]}',
            key="painel-claims-texto",
        )
        afirmacoes_arquivo = st.file_uploader(
            "Ou envie um arquivo JSON",
            type=["json"],
            key="painel-claims-arquivo",
        )
        contradicoes_texto = st.text_area(
            "Contradições (uma por linha, opcional)",
            height=80,
            key="painel-contradicoes",
        )
        st.caption(
            "O campo accessed_at de cada fonte é preenchido com a data e a hora "
            "do clique no botão do dossiê."
        )

    if st.button(
        rotulo,
        key="painel-montar-dossie",
        disabled=decisao != "approved",
        help="Exige a pauta aprovada." if decisao != "approved" else None,
    ):
        if afirmacoes_arquivo is not None and afirmacoes_texto.strip():
            st.error("Use o arquivo ou o texto de afirmações, não os dois.")
        else:
            bruto = (
                afirmacoes_arquivo.getvalue().decode("utf-8", errors="replace")
                if afirmacoes_arquivo is not None
                else afirmacoes_texto
            )
            processo: subprocess.CompletedProcess[str] | None = None
            try:
                payload = (
                    preparar_claims(_json_de_texto(bruto))
                    if bruto.strip()
                    else None
                )
            except (TypeError, ValueError) as exc:
                st.error(str(exc))
            else:
                with (
                    st.spinner("Validando afirmações e fontes..."),
                    tempfile.TemporaryDirectory() as temporaria,
                ):
                    argumentos = [
                        "dossie", "build", escolhida_id,
                        "--database", str(banco),
                    ]
                    if payload is not None:
                        caminho_claims = Path(temporaria) / "claims.json"
                        caminho_claims.write_text(
                            json.dumps(payload, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        argumentos += ["--claims", str(caminho_claims)]
                    for linha in contradicoes_texto.splitlines():
                        if linha.strip():
                            argumentos += ["--contradiction", linha.strip()]
                    processo = _cli(python, base, *argumentos)
            if processo is not None:
                resultado = _valores(processo, "Montar dossiê")
                if resultado is not None:
                    _aviso(f"Dossiê gravado: {resultado.get('recommendation')}.")
                    st.rerun()

    # --- 3. Minuta -----------------------------------------------------
    st.subheader(ETAPAS[2])
    rascunhos = _valores(_cli(python, base, "redacao", "list", "--database", str(banco)), "Listar minutas") or []
    do_tema = [
        rascunho
        for rascunho in rascunhos
        if rascunho.get("proposal_id") == escolhida_id
    ]

    pronto = bool(dossie) and dossie.get("recommendation") == "pronto para redação"
    if decisao != "approved":
        st.caption("A geração exige a pauta aprovada.")
    elif not pronto:
        st.caption(
            "A geração exige dossiê com recomendação 'pronto para redação'."
        )

    pode_gerar = pronto and decisao == "approved"
    if st.button(
        "Gerar minuta",
        key="painel-gerar-minuta",
        type="primary",
        disabled=not pode_gerar,
        help=None if pode_gerar else "Aprove a pauta e monte um dossiê suficiente.",
    ):
        with st.status(
            f"Redigindo com o modelo gratuito ({TEMPO_GERACAO})...", expanded=True
        ) as status:
            processo = _cli(python, base, "redacao", "gerar", escolhida_id, "--database", str(banco))
            if processo.returncode != 0:
                status.update(label="A geração falhou", state="error")
                _erro(processo, "Gerar minuta")
            else:
                status.update(label="Minuta gerada", state="complete")
                _aviso("Minuta gerada. Revise antes de decidir.")
                st.rerun()

    if not do_tema:
        if pronto:
            st.caption("Nenhuma minuta para esta pauta ainda.")
    else:
        ids = [rascunho["draft_id"] for rascunho in do_tema]
        minuta_id = st.selectbox(
            "Minuta",
            options=ids,
            format_func=lambda chave: (
                f"{chave[:8]} · "
                f"{next(r['created_at'] for r in do_tema if r['draft_id'] == chave)[:16]} · "
                f"{next(r['decision'] for r in do_tema if r['draft_id'] == chave)}"
            ),
            key="painel-minuta",
        )
        detalhe = _valores(
            _cli(python, base, "redacao", "mostrar", minuta_id, "--database", str(banco)),
            "Abrir minuta",
        )
        if detalhe:
            st.markdown(f"### {detalhe['draft'].get('title', '')}")
            if detalhe["draft"].get("subtitle"):
                st.markdown(f"*{detalhe['draft']['subtitle']}*")
            _corpo_minuta(detalhe["draft"])

            # --- 4. Revisão -------------------------------------------
            st.subheader(ETAPAS[3])
            _corpo_revisao(detalhe.get("review"))

            col_det, col_mod = st.columns(2)
            if col_det.button("Verificação automática", key="painel-revisar-det"):
                with st.spinner("Rodando as checagens determinísticas..."):
                    processo = _cli(
                        python, base, "redacao", "revisar", minuta_id,
                        "--deterministico", "--database", str(banco),
                    )
                resultado = _valores(processo, "Verificação automática")
                if resultado is not None:
                    _aviso(f"Verificação automática: {resultado.get('verdict')}.")
                    st.rerun()
            if col_mod.button(
                f"Revisar com o revisor ({TEMPO_GERACAO})", key="painel-revisar-modelo"
            ):
                with st.spinner(f"Revisor independente trabalhando ({TEMPO_GERACAO})..."):
                    processo = _cli(
                        python, base, "redacao", "revisar", minuta_id,
                        "--database", str(banco),
                    )
                resultado = _valores(processo, "Revisar com o revisor")
                if resultado is not None:
                    _aviso(f"Revisão concluída: {resultado.get('verdict')}.")
                    st.rerun()

            # --- 5. Decisão -------------------------------------------
            st.subheader(ETAPAS[4])
            revisao = detalhe.get("review")
            veredito = (revisao or {}).get("verdict")
            problemas = (revisao or {}).get("issues") or []
            graves = [
                problema
                for problema in problemas
                if problema.get("severity") in ("critico", "alto")
            ]

            if not revisao:
                st.caption("Revise a minuta antes de decidir.")
            elif veredito == "bloqueado":
                st.error(
                    "A revisão bloqueou esta minuta. A aprovação é recusada; "
                    "rejeite ou gere outro texto."
                )
            elif graves:
                st.error(
                    f"Atenção: {len(graves)} problema(s) de severidade alta ou "
                    "crítica. A aprovação é permitida, mas o texto vai para o "
                    "leitor com esses pontos em aberto."
                )
            elif veredito != "pronto_para_avaliacao_humana":
                st.warning(
                    "A revisão pediu ajustes. A aprovação é permitida; confira "
                    "os problemas acima antes."
                )

            if detalhe["draft"].get("editorial_decision") != "awaiting_human":
                st.info(
                    f"Decisão registrada: **{detalhe['draft']['editorial_decision']}**."
                )

            col_ok, col_no = st.columns(2)
            if col_ok.button(
                "Aprovar minuta",
                key="painel-aprovar-minuta",
                type="primary",
                disabled=veredito == "bloqueado",
            ):
                processo = _cli(
                    python, base, "redacao", "aprovar", minuta_id,
                    "--database", str(banco),
                )
                if _valores(processo, "Aprovar minuta") is not None:
                    _aviso(
                        "Minuta aprovada. Nada foi publicado: o portal não é "
                        "alcançado por este painel."
                    )
                    st.rerun()
            if col_no.button("Rejeitar minuta", key="painel-rejeitar-minuta"):
                processo = _cli(
                    python, base, "redacao", "rejeitar", minuta_id,
                    "--database", str(banco),
                )
                if _valores(processo, "Rejeitar minuta") is not None:
                    _aviso("Minuta rejeitada.", "warning")
                    st.rerun()
