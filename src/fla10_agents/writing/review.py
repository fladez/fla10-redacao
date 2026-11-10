"""Revisão independente e decisão humana sobre textos gerados."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import DraftArticle, ResearchDossier, ReviewIssue, ReviewReport
from fla10_agents.writing.context import load_writing_context, render_documents
from fla10_agents.writing.draft import parse_json_object
from fla10_agents.writing.provider import LLMProvider

PROMPT_VERSION = "review-v1"
BLOCKED_VERDICT = "bloqueado"
READY_VERDICT = "pronto_para_avaliacao_humana"
CHANGES_VERDICT = "ajustes_necessarios"

SYSTEM_PROMPT = """Você é o agente de Revisão e Controle de Qualidade da Redação Fla10.
Sua função é apontar problemas, não reescrever a matéria.
Verifique factualidade, atribuição, completude do formato, coerência, clareza,
redundância, estrutura, SEO, resumo para IA e formatação.
Não invente problemas nem fatos. Baseie cada apontamento no dossiê ou no texto.
Responda apenas com um objeto JSON válido."""

OUTPUT_SCHEMA = {
    "issues": [
        {
            "severity": "critico | alto | medio | baixo",
            "category": "factualidade | atribuicao | completude | formato | seo | html | estilo",
            "description": "problema objetivo",
            "evidence": "trecho do texto ou fato do dossiê",
        }
    ],
    "summary": "síntese curta da revisão",
}


class ReviewError(RuntimeError):
    """Falha segura na revisão ou na decisão sobre o texto."""


class ReviewOutput(BaseModel):
    issues: list[ReviewIssue]
    summary: str = ""


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return without_accents.casefold()


def build_review_prompt(
    draft: DraftArticle,
    dossier: ResearchDossier,
    documents: str,
    deterministic_issues: list[ReviewIssue],
) -> str:
    existing = [
        issue.model_dump(mode="json")
        for issue in deterministic_issues
    ]

    return f"""# Documentos editoriais canônicos

{documents}

# Texto para revisão

```json
{draft.model_dump_json(indent=2)}
```

# Dossiê de apuração

```json
{dossier.model_dump_json(indent=2)}
```

# Achados automáticos já registrados

```json
{json.dumps(existing, ensure_ascii=False, indent=2)}
```

# Tarefa

Revise o texto contra o dossiê e o checklist do formato `{draft.format}`.
Não repita achados automáticos idênticos. Aponte apenas problemas verificáveis.
Não reescreva o texto. Classifique a gravidade:
- `critico`: fato inventado, afirmação sem suporte central ou risco grave;
- `alto`: informação importante ausente, atribuição inadequada ou erro factual;
- `medio`: problema de completude, formato ou clareza que exige ajuste;
- `baixo`: melhoria editorial sem bloquear.

# Esquema de saída

Responda somente com JSON válido neste formato:

```json
{json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}
```
"""


def deterministic_issues(draft: DraftArticle) -> tuple[list[ReviewIssue], list[str]]:
    issues: list[ReviewIssue] = []
    checks: list[str] = []
    body = _normalize(draft.body_markdown)

    def add(severity: str, category: str, description: str) -> None:
        issues.append(
            ReviewIssue(
                severity=severity,  # type: ignore[arg-type]
                category=category,
                description=description,
            )
        )

    checks.append("título, subtítulo e corpo preenchidos")
    if not draft.title.strip():
        add("critico", "completude", "Título ausente.")
    if not draft.subtitle.strip():
        add("alto", "completude", "Subtítulo ausente.")
    if len(draft.body_markdown.strip()) < 200:
        add("alto", "completude", "Corpo curto demais para publicação.")

    checks.append("resumo para IA e pacote SEO preenchidos")
    if not (draft.ai_summary or "").strip():
        add("alto", "formato", "Resumo para IA ausente.")
    if not draft.seo.title.strip() or not draft.seo.meta_description.strip():
        add("alto", "seo", "Título SEO ou meta description ausente.")
    if not draft.seo.primary_keyword.strip():
        add("medio", "seo", "Palavra-chave principal ausente.")

    checks.append("sem marcadores de preenchimento")
    if re.search(r"\[(?:inserir|preencher|todo|xxx)\]|\bTODO\b", draft.body_markdown, re.IGNORECASE):
        add("alto", "completude", "Corpo contém marcador de preenchimento.")

    checks.append("sem fontes ou URLs no corpo publicável")
    if "http://" in body or "https://" in body or "fonte:" in body:
        add("medio", "formato", "Corpo publicável contém fonte ou URL.")

    if _normalize(draft.title.strip()) == _normalize(draft.subtitle.strip()):
        add("medio", "estilo", "Título e subtítulo são iguais.")

    if draft.format == "onde_assistir":
        checks.append("checklist de Onde Assistir")
        if "transmiss" not in body and "onde assistir" not in body:
            add("alto", "formato", "Transmissão ou serviço de onde assistir não informado.")
        if "horario" not in body:
            add("alto", "formato", "Horário do jogo não informado.")
        if "estadio" not in body and "local" not in body:
            add("medio", "formato", "Estádio ou local não informado.")
        if "arbitrag" not in body:
            add("medio", "formato", "Arbitragem não mencionada, nem a ausência de divulgação.")
        if "escalac" not in body:
            add("medio", "formato", "Escalações não mencionadas, nem a ausência de confirmação.")

    return issues, checks


def _verdict(issues: list[ReviewIssue]) -> str:
    severities = {issue.severity for issue in issues}

    if "critico" in severities:
        return BLOCKED_VERDICT
    if severities & {"alto", "medio"}:
        return CHANGES_VERDICT
    return READY_VERDICT


def _normalize_review_output(payload: dict[str, Any]) -> ReviewOutput:
    items = payload.get("issues", [])
    if not isinstance(items, list):
        raise ReviewError("A revisão não retornou uma lista de problemas.")

    aliases = {
        "crítico": "critico",
        "critica": "critico",
        "médio": "medio",
        "media": "medio",
        "baixa": "baixo",
        "alta": "alto",
    }
    normalized: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            raise ReviewError("A revisão retornou um problema em formato inválido.")

        data = dict(item)
        severity = str(data.get("severity", "")).strip().casefold()
        data["severity"] = aliases.get(severity, severity)
        normalized.append(data)

    try:
        return ReviewOutput.model_validate({"issues": normalized, "summary": payload.get("summary", "")})
    except ValueError as exc:
        raise ReviewError(f"Problemas retornados pela revisão são inválidos: {exc}") from exc


def review_draft(
    editorial_database: str | Path,
    draft_id: str,
    provider: LLMProvider | None,
    *,
    model: str,
    vault_root: Path | None = None,
    max_tokens: int = 3000,
    now: datetime | None = None,
) -> ReviewReport:
    """Aplica checagens determinísticas e, se configurado, revisão por LLM."""
    reference = now or datetime.now(UTC)

    with EditorialRepository(editorial_database) as store:
        draft = store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"Texto não encontrado: {draft_id}")

        dossier = store.get_dossier(draft.proposal_id)
        if dossier is None:
            raise ReviewError("O texto não tem dossiê associado.")

        local_issues, checks = deterministic_issues(draft)
        issues = list(local_issues)
        summary = ""
        generation: dict[str, object] = {}
        prompt_sha = None

        if provider is not None:
            context = load_writing_context(draft.format, vault_root)
            prompt = build_review_prompt(
                draft,
                dossier,
                render_documents(context),
                local_issues,
            )
            response = provider.complete(
                prompt,
                model=model,
                system=SYSTEM_PROMPT,
                max_tokens=max_tokens,
                temperature=0.1,
            )
            output = _normalize_review_output(parse_json_object(response.text))
            issues.extend(output.issues)
            summary = output.summary
            prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            generation = {
                "served_model": response.served_model,
                "usage": response.usage,
                "elapsed_seconds": response.elapsed_seconds,
                "vault_commit": context.commit,
            }
        else:
            checks.append("revisão por LLM desativada")

        report = ReviewReport(
            draft_id=draft_id,
            verdict=_verdict(issues),
            issues=issues,
            checks=checks,
            summary=summary,
            reviewer_model=model if provider is not None else "deterministico",
            prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha,
            generation=generation,
            reviewed_at=reference,
        )
        store.save_review(report)

    return report


def decide_draft(
    editorial_database: str | Path,
    draft_id: str,
    decision: str,
) -> DraftArticle:
    """Registra a decisão humana, bloqueando aprovação de texto bloqueado."""
    with EditorialRepository(editorial_database) as store:
        draft = store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"Texto não encontrado: {draft_id}")

        if decision == "approved":
            review = store.get_latest_review(draft_id)
            if review is None:
                raise ReviewError("Revise o texto antes de aprová-lo.")
            if review.verdict == BLOCKED_VERDICT:
                raise ReviewError(
                    "O texto está bloqueado pela revisão e não pode ser aprovado."
                )

        return store.decide_draft(draft_id, decision)
