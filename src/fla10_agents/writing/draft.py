"""Geração de texto a partir de pauta aprovada e dossiê suficiente."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from fla10_agents.editorial.store import EditorialRepository
from fla10_agents.models import (
    DraftArticle,
    EditorialProposal,
    EvidenceSource,
    ResearchDossier,
    SeoPackage,
)
from fla10_agents.writing.context import load_writing_context, render_documents
from fla10_agents.writing.provider import LLMProvider

PROMPT_VERSION = "writing-v1"
REQUIRED_DOSSIER_RECOMMENDATION = "pronto para redação"
MIN_BODY_CHARS = 200

SYSTEM_PROMPT = """Você é o agente de Produção da Redação Fla10.
Escreve em português do Brasil, com precisão factual e voz editorial própria.
Regras invioláveis:
- use somente fatos presentes no dossiê e na pauta;
- não invente datas, números, falas, fontes, escalações, arbitragem ou transmissão;
- se uma informação não estiver no dossiê, diga que não foi divulgada ou omita;
- não transforme hipótese, estimativa ou relato atribuído em fato confirmado;
- não afirme que a matéria foi publicada;
- não inclua URLs de fontes no corpo publicável;
- responda apenas com um objeto JSON válido, sem texto fora do JSON."""

OUTPUT_SCHEMA = {
    "title": "título jornalístico",
    "subtitle": "subtítulo que acrescenta contexto",
    "body_markdown": "corpo completo em Markdown, com subtítulos internos usando ##",
    "ai_summary": "resumo factual e autossuficiente para IA",
    "seo": {
        "title": "título SEO",
        "meta_description": "meta description",
        "primary_keyword": "palavra-chave principal",
        "secondary_keywords": ["palavra secundária"],
    },
    "social_posts": ["texto curto para redes, sem inventar fato"],
}


class WritingError(RuntimeError):
    """Falha segura na geração ou validação do texto."""


class WritingOutput(BaseModel):
    title: str
    subtitle: str
    body_markdown: str
    ai_summary: str
    seo: SeoPackage
    social_posts: list[str] = Field(default_factory=list)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extrai um objeto JSON mesmo se vier cercado por bloco de código."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise WritingError("O modelo não retornou um objeto JSON reconhecível.")

    try:
        data = json.loads(stripped[start : end + 1])
    except ValueError as exc:
        raise WritingError("O JSON retornado pelo modelo é inválido.") from exc

    if not isinstance(data, dict):
        raise WritingError("O modelo retornou JSON que não é um objeto.")

    return data


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)


def render_site_html(markdown: str) -> str:
    """Converte Markdown simples no padrão HTML da Redação Fla10."""
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(_inline_markdown(" ".join(paragraph)))
            paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()

        if not line:
            flush()
            continue

        if line.startswith("## "):
            flush()
            blocks.append(f"<h3>{_inline_markdown(line[3:].strip())}</h3>")
            continue

        if line.startswith("### "):
            flush()
            blocks.append(f"<h3>{_inline_markdown(line[4:].strip())}</h3>")
            continue

        paragraph.append(line)

    flush()
    return "<br><br>".join(block for block in blocks if block)


def _collect_sources(dossier: ResearchDossier) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    seen: set[str] = set()

    for claim in dossier.claims:
        for source in claim.evidence:
            key = str(source.url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)

    return sources


def build_writing_prompt(
    proposal: EditorialProposal,
    dossier: ResearchDossier,
    documents: str,
) -> str:
    format_rules = ""
    if proposal.format == "onde_assistir":
        format_rules = (
            "Checklist do formato Onde Assistir: data e horário; competição e fase; "
            "canais/plataformas confirmados; estádio e mando; prováveis escalações "
            "atribuídas; arbitragem verificada ou ausência de divulgação informada; "
            "contexto; resumo para IA; pacote SEO. Se transmissão ou arbitragem não "
            "estiverem no dossiê, escreva explicitamente que não foram divulgadas."
        )
    elif proposal.format == "ultimas_noticias":
        format_rules = (
            "Formato Últimas Notícias: título com o fato central; subtítulo com "
            "consequência ou contexto; abertura responde o que aconteceu, com quem "
            "e por que importa; desenvolvimento com confirmação, contexto e próximos "
            "passos; resumo para IA; pacote SEO. Não use 'última hora' sem motivo real."
        )

    return f"""# Documentos editoriais canônicos

{documents}

# Pauta aprovada

```json
{proposal.model_dump_json(indent=2)}
```

# Dossiê de apuração

```json
{dossier.model_dump_json(indent=2)}
```

# Tarefa

Escreva a matéria completa para o formato `{proposal.format}`.
{format_rules}

Use os fatos utilizáveis do dossiê. Informações atribuídas devem ser atribuídas
nominalmente. Não use afirmações excluídas nem hipóteses como fato. O corpo deve
ter subtítulos internos com `##`. O resumo para IA deve ser autossuficiente e não
pode acrescentar fato ausente do corpo.

# Esquema de saída

Responda somente com JSON válido neste formato:

```json
{json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}
```
"""


def _validate_output(output: WritingOutput) -> None:
    title = output.title.strip()
    subtitle = output.subtitle.strip()
    body = output.body_markdown.strip()
    summary = output.ai_summary.strip()

    if len(title) < 10:
        raise WritingError("O título gerado é curto demais.")
    if len(subtitle) < 10:
        raise WritingError("O subtítulo gerado é curto demais.")
    if len(body) < MIN_BODY_CHARS:
        raise WritingError("O corpo gerado é curto demais.")
    if not summary:
        raise WritingError("O resumo para IA está vazio.")
    if not output.seo.title.strip() or not output.seo.meta_description.strip():
        raise WritingError("O pacote SEO está incompleto.")
    if not output.seo.primary_keyword.strip():
        raise WritingError("A palavra-chave principal está vazia.")

    placeholder = re.compile(r"\[(?:inserir|preencher|todo|xxx)\]|\bTODO\b", re.IGNORECASE)
    if placeholder.search(body):
        raise WritingError("O corpo contém marcador de preenchimento.")


def generate_draft(
    editorial_database: str | Path,
    proposal_id: str,
    provider: LLMProvider,
    *,
    model: str,
    vault_root: Path | None = None,
    max_tokens: int = 8000,
    temperature: float = 0.2,
    now: datetime | None = None,
) -> DraftArticle:
    """Gera e persiste um texto; não aprova nem publica."""
    reference = now or datetime.now(UTC)

    with EditorialRepository(editorial_database) as store:
        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Pauta não encontrada: {proposal_id}")

        if proposal.editorial_decision != "approved":
            raise WritingError(
                "A pauta precisa estar aprovada antes da produção. "
                f"Estado atual: {proposal.editorial_decision}."
            )

        dossier = store.get_dossier(proposal_id)
        if dossier is None:
            raise WritingError("A pauta não tem dossiê de apuração.")
        if dossier.recommendation != REQUIRED_DOSSIER_RECOMMENDATION:
            raise WritingError(
                "O dossiê não está pronto para redação. "
                f"Recomendação atual: {dossier.recommendation}."
            )

        context = load_writing_context(proposal.format, vault_root)
        prompt = build_writing_prompt(
            proposal,
            dossier,
            render_documents(context),
        )

        response = provider.complete(
            prompt,
            model=model,
            system=SYSTEM_PROMPT,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        try:
            output = WritingOutput.model_validate(parse_json_object(response.text))
        except WritingError:
            raise
        except ValueError as exc:
            raise WritingError(f"Saída do modelo inválida: {exc}") from exc
        _validate_output(output)

        draft = DraftArticle(
            proposal_id=proposal_id,
            format=proposal.format,
            title=output.title.strip(),
            subtitle=output.subtitle.strip(),
            body_markdown=output.body_markdown.strip(),
            body_html=render_site_html(output.body_markdown),
            ai_summary=output.ai_summary.strip(),
            seo=output.seo,
            social_posts=output.social_posts,
            sources=_collect_sources(dossier),
            model=model,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            generation={
                "served_model": response.served_model,
                "usage": response.usage,
                "elapsed_seconds": response.elapsed_seconds,
                "vault_commit": context.commit,
                "documents": sorted(context.files),
            },
            created_at=reference,
        )
        store.save_draft(draft)

    return draft
