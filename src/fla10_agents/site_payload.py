"""Converte o pacote de CMS no documento `news` do site FLA10 News.

O site (Next.js) lê a coleção `news` do Firestore. Este módulo só monta o
documento e lista as pendências: nada é gravado no banco nem publicado.
"""

from __future__ import annotations

from typing import Any

from fla10_agents.models import PublicationPackage

CATEGORIA_PRINCIPAL = "Futebol"
COLECAO_DESTINO = "news"
DICA_IMAGEM = "flamengo futebol"


def subcategoria(titulo: str, corpo: str) -> str:
    """Sugere a tag do site a partir do próprio texto, sem inventar assunto."""
    texto = f"{titulo} {corpo}".lower()
    if "feminin" in texto:
        return "Feminino"
    if "sub-2" in texto or "categoria de base" in texto or "categorias de base" in texto:
        return "Base"
    return "Profissional"


def documento_do_site(package: PublicationPackage) -> dict[str, Any]:
    """Documento no formato aceito pela coleção `news` do site."""
    return {
        "mainCategory": CATEGORIA_PRINCIPAL,
        "title": package.title,
        "excerpt": package.subtitle or package.ai_summary or "",
        "category": subcategoria(package.title, package.body_markdown),
        "content": package.body_html,
        "slug": package.slug,
        "image": "",
        "dataAiHint": DICA_IMAGEM,
        "author": "",
        "status": "draft",
        # Nulo: o site usa o horário da criação; a matéria ainda não foi publicada.
        "publishedAt": None,
        "views": 0,
        "metaTitle": package.seo.title,
        "metaDescription": package.seo.meta_description,
        "focusKeyword": package.seo.primary_keyword,
        "secondaryKeywords": ", ".join(package.seo.secondary_keywords),
    }


def pendencias_do_site(package: PublicationPackage) -> list[str]:
    """O que uma pessoa precisa preencher antes de criar a matéria no site."""
    itens = ["Informe a URL da imagem de capa (16:9): o site exige o campo."]
    if not package.subtitle.strip():
        itens.append(
            "O texto não tem subtítulo: o excerpt usou o resumo para IA; revise o campo."
        )
    itens.append("Confira a subcategoria sugerida (Profissional, Feminino ou Base).")
    itens.append("Autor: informe o nome ou deixe o padrão do site.")
    itens.append("A matéria entra como rascunho; publicar é uma ação humana no painel.")
    return itens


def pacote_do_site(package: PublicationPackage) -> dict[str, Any]:
    """Envelope do documento com as pendências e o destino."""
    return {
        "destino": f"coleção {COLECAO_DESTINO} do Firestore (site FLA10 News)",
        "documento": documento_do_site(package),
        "pendencias": pendencias_do_site(package),
    }
