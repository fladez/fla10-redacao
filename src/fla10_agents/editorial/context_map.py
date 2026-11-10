"""Mapa dos documentos canônicos do Redacao-Fla10 por tipo de tarefa."""

BOOTSTRAP_FILES = (
    "AGENTS.md",
    "README.md",
    "00 - Sistema/Índice.md",
    "00 - Sistema/Protocolo de Operação da IA.md",
)

TASK_DOCUMENTS: dict[str, tuple[str, ...]] = {
    "calendar": (
        "02 - Operação/Fluxo de Produção.md",
        "02 - Operação/Gestão de Pautas.md",
        "06 - Pautas/Painel de Pautas.md",
        "02 - Operação/Pesquisa e Fontes.md",
        "08 - Fontes e Referências/Critérios de Confiabilidade.md",
    ),
    "monitoring": (
        "01 - Manual Editorial/Identidade Editorial.md",
        "01 - Manual Editorial/Apuração e Integridade Factual.md",
        "02 - Operação/Gestão de Pautas.md",
        "02 - Operação/Pesquisa e Fontes.md",
        "02 - Operação/Prevenção de Redundância Editorial.md",
        "06 - Pautas/Painel de Pautas.md",
        "06 - Pautas/Projetos e Pautas Reservadas.md",
        "08 - Fontes e Referências/Critérios de Confiabilidade.md",
        "09 - Modelos/Modelo de Briefing de Pauta.md",
    ),
    "research": (
        "01 - Manual Editorial/Apuração e Integridade Factual.md",
        "02 - Operação/Pesquisa e Fontes.md",
        "08 - Fontes e Referências/Critérios de Confiabilidade.md",
        "09 - Modelos/Modelo de Ficha de Apuração.md",
    ),
    "where_to_watch": (
        "01 - Manual Editorial/Apuração e Integridade Factual.md",
        "01 - Manual Editorial/Estilo e Formatação.md",
        "03 - Formatos/Onde Assistir.md",
        "01 - Manual Editorial/Revisão e Controle de Qualidade.md",
    ),
}
