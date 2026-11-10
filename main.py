import argparse
import os
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as xml_etree

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
from dotenv import load_dotenv

import resultados
from opencode_llm import OpenCodeLLM
from versoes import salvar_versoes, separar_versoes

# 1. Carregar variáveis de ambiente
load_dotenv()

# 2. Motor gratuito do OpenBot: DeepSeek V4.1 Flash Free pelo OpenCode local.
#    Não usa provedor pago, não exige chave de API e tem custo zero.
MODELO = OpenCodeLLM()

# 3. Estratégia de apuração.
#    Padrão (0): a busca é feita aqui, em Python, e os resultados entram na tarefa.
#    Alternativa (1): o agente usa a ferramenta busca_web no laço ReAct do CrewAI.
USAR_REACT = os.getenv("FLA10_USAR_REACT", "0").strip() == "1"

# 4. Tema da pauta e coleta determinística de fatos.
PAUTA_PADRAO = "Último jogo do Flamengo no Brasileirão (resultado, gols, destaques e declarações)"


def ler_pauta(argv: list[str] | None = None) -> str:
    """Pauta pelo argumento posicional, por FLA10_PAUTA ou pelo padrão."""
    parser = argparse.ArgumentParser(
        description="Redação automatizada do FLA10 News (6 agentes, sequencial)."
    )
    parser.add_argument(
        "pauta",
        nargs="?",
        help="Tema da matéria. Sem argumento, usa FLA10_PAUTA ou a pauta padrão.",
    )
    args = parser.parse_args(argv)
    return (args.pauta or os.getenv("FLA10_PAUTA", "")).strip() or PAUTA_PADRAO


tema_pesquisa = ler_pauta()

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={consulta}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)
MAX_NOTICIAS_APURACAO = 20
EPOCH = datetime.min.replace(tzinfo=UTC)


def _data_local(texto: str) -> datetime | None:
    """Converte a data do RSS (GMT) para o fuso local; inválida vira None."""
    try:
        return parsedate_to_datetime(texto).astimezone()
    except (TypeError, ValueError, IndexError):
        return None


def _buscar_itens(consulta: str, limite: int = 8) -> list[dict]:
    """Lê o RSS do Google News e devolve as notícias mais recentes da consulta."""
    url = GOOGLE_NEWS_RSS.format(consulta=urllib.parse.quote(consulta))
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requisicao, timeout=25) as resposta:
        raiz = xml_etree.fromstring(resposta.read())

    itens = []
    for item in raiz.findall(".//item"):
        titulo = (item.findtext("title") or "").strip()
        if not titulo:
            continue
        resumo = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        itens.append(
            {
                "titulo": titulo,
                "fonte": (item.findtext("source") or "").strip() or "fonte não informada",
                "quando": _data_local((item.findtext("pubDate") or "").strip()),
                "resumo": re.sub(r"\s+", " ", resumo).strip()[:350],
            }
        )

    itens.sort(key=lambda noticia: noticia["quando"] or EPOCH, reverse=True)
    return itens[:limite]


def _formatar_item(noticia: dict) -> str:
    quando = noticia["quando"]
    carimbo = quando.strftime("%d/%m/%Y %H:%M") if quando else "data desconhecida"
    return (
        f"- {carimbo} | {noticia['fonte']} | {noticia['titulo']}: "
        f"{noticia['resumo']}"
    )


def buscar_noticias(consulta: str, limite: int = 8) -> list[str]:
    """Busca notícias reais no Google News RSS, sem chave de API."""
    return [_formatar_item(item) for item in _buscar_itens(consulta, limite)]


def coletar_apuracao(tema: str) -> tuple[str, list[str]]:
    """Junta notícias de várias consultas, sem repetir manchete, da mais nova à mais antiga."""
    consultas = [tema]
    if "flamengo" not in tema.lower():
        consultas.append(f"Flamengo {tema}")
    consultas.append("Flamengo escalação e declarações pós-jogo")
    itens: list[dict] = []
    vistos: set[str] = set()
    falhas: list[str] = []

    for consulta in consultas:
        try:
            novas = _buscar_itens(consulta)
        except Exception as erro:  # noqa: BLE001 - rede fora do ar não deve derrubar o pipeline
            falhas.append(f"{consulta}: {erro}")
            continue
        for noticia in novas:
            if noticia["titulo"] in vistos:
                continue
            vistos.add(noticia["titulo"])
            itens.append(noticia)

    if not itens:
        return "", falhas

    itens.sort(key=lambda noticia: noticia["quando"] or EPOCH, reverse=True)
    linhas = [_formatar_item(item) for item in itens[:MAX_NOTICIAS_APURACAO]]
    return "\n".join(linhas), falhas


# 5. Ferramenta de busca (usada apenas quando FLA10_USAR_REACT=1)
@tool("Busca na Web")
def busca_web(query: str) -> str:
    """Busca notícias reais no Google News e devolve os resultados formatados."""
    try:
        linhas = buscar_noticias(query, limite=5)
        if not linhas:
            return "Nenhuma notícia encontrada para esta consulta."
        return "\n".join(linhas)
    except Exception as e:  # noqa: BLE001 - falha de rede vira texto para o agente
        return f"Erro ao realizar a busca: {e}"

# 4. Definição dos Agentes (Personas do FLA10)
agentes = {
    "apurador": Agent(
        role="Apurador de Fatos do FLA10",
        goal="Levantar as informações mais recentes e relevantes sobre o último jogo do Flamengo, sem inventar dados.",
        backstory="Você é um repórter de campo rápido e preciso. Sua missão é coletar dados brutos: placar, gols, escalações, declarações pós-jogo e estatísticas.",
        tools=[busca_web] if USAR_REACT else [],
        llm=MODELO,
        verbose=False
    ),
    "plantao": Agent(
        role="Repórter de Plantão (Hard News)",
        goal="Escrever uma matéria direta, factual e informativa.",
        backstory="Estilo hard news: pirâmide invertida, lead com 5W2H no primeiro parágrafo, sem adjetivos desnecessários. Foco total nos fatos.",
        llm=MODELO,
        verbose=False
    ),
    "tatico": Agent(
        role="Analista Tático (Raio-X)",
        goal="Escrever uma análise técnica e detalhada do jogo.",
        backstory="Estilo Raio-X Tático: foco em linhas de passe, movimentação, dados de posse e decisões do técnico. Linguagem técnica mas acessível ao torcedor.",
        llm=MODELO,
        verbose=False
    ),
    "cronista": Agent(
        role="Cronista Rubro-Negro (Opinião)",
        goal="Escrever um texto literário, apaixonado e com voz autoral.",
        backstory="Estilo crônica esportiva: texto envolvente, metáforas, foco na emoção, na 'Nação' e no drama do futebol, similar às colunas de opinião do site.",
        llm=MODELO,
        verbose=False
    ),
    "nacao": Agent(
        role="Comunicador da Nação (Popular)",
        goal="Escrever um texto vibrante, engajador e com a linguagem da torcida.",
        backstory="Estilo popular: uso de gírias rubro-negras ('Mengão', 'Urubu'), frases de efeito, foco no impacto emocional e na festa da torcida.",
        llm=MODELO,
        verbose=False
    ),
    "revisor": Agent(
        role="Copydesk / Revisor Chefe do FLA10",
        goal="Revisar, formatar e garantir a qualidade final de todas as versões da matéria.",
        backstory="Você é o guardião da qualidade do FLA10 News. Verifica gramática, ortografia, coerência e se cada texto respeitou a persona proposta. Formata a saída final em Markdown limpo.",
        llm=MODELO,
        verbose=False
    )
}

# 6. Definição das Tarefas
if USAR_REACT:
    descricao_apuracao = (
        f"Use a ferramenta de busca na web para pesquisar sobre: '{tema_pesquisa}'. "
        "Traga um resumo estruturado com: Placar, Gols, Destaques individuais, "
        "Declarações pós-jogo e Contexto na tabela."
    )
else:
    print("🔎 Coletando resultado oficial (Cartola/ge.globo)...")
    ficha, erro_ficha = resultados.coletar()
    if ficha:
        print("   " + ficha.replace("\n", " | ") + "\n")
    else:
        print(f"   {erro_ficha}\n")

    print("🔎 Coletando notícias no Google News (sem chave de API)...")
    fatos, falhas = coletar_apuracao(tema_pesquisa)
    if fatos:
        print(f"   {len(fatos.splitlines())} trechos coletados.\n")
    else:
        detalhe = (" Falhas: " + " | ".join(falhas)) if falhas else ""
        print(f"   Nenhuma notícia encontrada.{detalhe}\n")

    blocos = []
    if ficha:
        blocos.append(
            "--- FICHA OFICIAL DO ÚLTIMO JOGO (início) ---\n"
            f"{ficha}\n"
            "--- FICHA OFICIAL DO ÚLTIMO JOGO (fim) ---"
        )
    if fatos:
        blocos.append(
            "--- NOTÍCIAS COLETADAS (início) ---\n"
            f"{fatos}\n"
            "--- NOTÍCIAS COLETADAS (fim) ---"
        )

    if blocos:
        descricao_apuracao = (
            "O material abaixo já foi coletado automaticamente. "
            "NÃO chame ferramentas e NÃO invente dados.\n\n"
            + "\n\n".join(blocos)
            + "\n\nCom base SOMENTE nesse material, monte um relatório estruturado com: "
            "Placar, Gols, Destaques individuais, Declarações pós-jogo e Contexto na tabela. "
            "Indique a data e a fonte de cada informação. Se algum campo não aparecer "
            "no material, escreva 'não encontrado' em vez de supor.\n\n"
            "A FICHA OFICIAL tem prioridade sobre as notícias: use exatamente o placar, "
            "as equipes e a data dela e descarte qualquer resultado divergente. "
            "A lista 'Entraram em campo' mostra quem atuou, não a escalação titular: "
            "não a apresente como time titular nem invente posições."
        )
    else:
        descricao_apuracao = (
            "A coleta automática não retornou notícias nem resultado oficial. "
            "Informe isso explicitamente e NÃO invente placar, gols, escalações, "
            "declarações ou estatísticas."
        )

tarefa_apuracao = Task(
    description=descricao_apuracao,
    agent=agentes["apurador"],
    expected_output="Um relatório factual e estruturado com todos os dados da partida."
)

def criar_tarefa_redacao(nome_agente, estilo):
    return Task(
        description=f"Com base no relatório de apuração, escreva uma matéria completa sobre o jogo no estilo '{estilo}'. Inclua um Título Chamativo e o Corpo do Texto.",
        agent=agentes[nome_agente],
        expected_output=f"Matéria completa em Markdown, estilo {estilo}."
    )

tarefas_redacao = [
    criar_tarefa_redacao("plantao", "Hard News (Direto e Factual)"),
    criar_tarefa_redacao("tatico", "Análise Tática (Raio-X)"),
    criar_tarefa_redacao("cronista", "Crônica Opinativa (Literário e Apaixonado)"),
    criar_tarefa_redacao("nacao", "Linguagem Popular e Engajadora")
]

tarefa_revisao = Task(
    description=(
        "Pegue TODAS as 4 versões de matérias geradas pelos redatores. Revise cada uma "
        "delas, corrigindo eventuais erros de português e garantindo que o estilo "
        "solicitado foi respeitado. Mantenha o resultado fiel ao relatório de apuração: "
        "não acrescente placar, gols ou declarações que não estejam nele.\n\n"
        "Formato obrigatório de saída: antes de cada versão escreva, sozinha na linha, "
        "uma marcação exatamente assim: <!-- VERSAO:1 --> e assim por diante até 4, na "
        "ordem em que as versões foram geradas (1 notícia, 2 análise tática, 3 crônica, "
        "4 popular). Não use '---' como separador entre versões nem dentro dos textos; "
        "para separar seções dentro de um texto use '###'."
    ),
    agent=agentes["revisor"],
    expected_output=(
        "Um documento Markdown com 4 versões revisadas, cada uma precedida por "
        "<!-- VERSAO:n -->, prontas para publicação no FLA10 News."
    )
)




# 7. Montagem e Execução da Crew
print("🚀 Iniciando a Redação Automatizada do FLA10 News...\n")
print(f"📝 Pauta: {tema_pesquisa}\n")
print("🔍 Fase 1: Apurando os fatos na web (isso pode levar ~30 segundos)...\n")

redacao_fl10 = Crew(
    agents=list(agentes.values()),
    tasks=[tarefa_apuracao] + tarefas_redacao + [tarefa_revisao],
    process=Process.sequential,
    verbose=True # Mostra o passo a passo no terminal
)

resultado = redacao_fl10.kickoff()

print("\n" + "="*70)
print("✅ PROCESSO CONCLUÍDO COM SUCESSO!")
print("📰 Aqui estão as matérias prontas para sua aprovação:\n")
print("="*70)
print(resultado.raw)

versoes = separar_versoes(resultado.raw)
if len(versoes) == 4:
    print(f"\n✅ 4 versões identificadas: {', '.join(str(n) for n, _ in versoes)}")
else:
    print(
        f"\n⚠️  Esperava 4 versões e encontrei {len(versoes)}. "
        "Confira o texto acima antes de publicar."
    )
pasta = salvar_versoes(resultado.raw, versoes)
print(f"📁 Arquivos salvos em {pasta.resolve()}")