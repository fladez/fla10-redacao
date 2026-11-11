# 15 — Entrega operacional

Guia para operar a Redação FLA10 no dia a dia. Cobre o que já está pronto, o
que continua manual e o que fazer quando algo falha. Nenhuma etapa publica
conteúdo no site sozinha.

## 0. Escopo inicial (definido em 11/11/2026)

O sistema **pesquisa pautas e redige minutas. Nada é publicado no portal.**

| Entrega | Situação |
|---|---|
| Pesquisa de pautas | ✅ busca RSS + ficha do jogo + pipeline Fase 1 (sinais, propostas, dossiê) |
| Minutas de matéria | ✅ `fla10 redacao gerar` → `revisar` → decisão humana |
| Pacote de CMS | ⚪ gera local (`publicacao preparar/exportar`), nunca é enviado |
| Publicação no portal | ❌ fora do escopo; continua manual e não faz parte do fluxo |

O que muda na prática: a aprovação registra a decisão editorial, mas não
dispara nada. O caminho `site-news.json` → Firestore continua existindo no
código e continua sem ser executado automaticamente.

## 1. O que está entregue

- Pipeline de 6 agentes em sequência (`Process.sequential`): Apurador,
  Repórter de Plantão, Analista Tático, Cronista, Comunicador da Nação e
  Revisor.
- Quatro versões por execução, salvas em arquivos separados.
- Apuração determinística em Python: ficha oficial do último jogo (API do
  Cartola FC/ge) e notícias recentes (RSS do Google News).
- Interface local em Streamlit com duas áreas: o pipeline de 6 agentes
  (pauta, geração, abas, downloads, abertura de execuções antigas e
  aprovação) e o fluxo por pauta (propostas, dossiê, minuta, revisão e
  decisão).
- Verificação automática de qualidade das versões antes da aprovação.
- Pacote de CMS com `article.md`, `article.html`, `package.json`,
  `metadata.json` e `site-news.json` (documento `news` para o Firestore).
- Rotina diária no OpenBot (07:00) que gera as propostas de pauta da agenda,
  sem modelo e sem custo. As rotinas pós-jogo existem, mas estão desativadas
  enquanto o escopo for pesquisa e minuta.
- Testes, Ruff e mypy no CI (`.github/workflows/tests.yml`), em Python 3.11 e
  3.12.

## 2. Pré-requisitos

| Item | Valor usado na entrega |
|---|---|
| Python do pipeline e da interface | 3.11.18 |
| Interpretador | `/Users/rcorreas/miniconda3/envs/fla10/bin/python` |
| Runtime do OpenCode | `~/Library/Application Support/OpenBot/provider-runtimes/opencode/darwin-x64/2.2.7/bin/opencode` |
| Modelo | `opencode/deepseek-v4.1-flash-free` |
| Custo | zero (cota gratuita do OpenCode) |

Instalação do ambiente do pipeline:

```bash
python -m pip install -r requirements-pipeline.txt
```

As dependências do pacote Python (CLI, testes, lint) ficam no `pyproject.toml`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # CLI, testes, Ruff, mypy
pip install -e ".[ui]"         # opcional: Streamlit
```

O CrewAI não é instalado no venv da CLI: ele só é necessário para o `main.py`,
que roda no interpretador do pipeline.

## 3. Fluxo diário

1. O jogo termina.
2. Às 23:30 (ou 08:00, como rede de segurança), a rotina do OpenBot verifica a
   ficha do último jogo.
3. Se o jogo terminou nas últimas 14 horas e ainda não foi redigido, a rotina
   chama o `main.py` e avisa com placar, pasta e quantidade de versões.
4. O editor abre a interface, lê as quatro versões e aprova uma.
5. A aprovação grava `aprovada.json` e gera o pacote de CMS.
6. O editor cria a matéria no painel do site com o texto e a imagem; nada é
   gravado no Firestore pelo sistema.

Tempo esperado do passo 3: de 7 a 10 minutos, com 6 chamadas ao modelo.

### Fluxo por pauta (área "Pautas e minutas" do painel)

Para pauta que não vem de jogo — e para a minuta a partir da agenda — o painel
tem a área **Pautas e minutas**, em cinco etapas:

1. **Propostas** — gera as propostas da agenda e do vault e mostra formato,
   janela, prioridade e risco de redundância. Aprovar aqui é decisão local.
2. **Dossiê** — um clique monta o dossiê a partir dos fatos confirmados da
   pauta e das fontes do evento; lista fatos utilizáveis, lacunas e
   contradições. Sem fonte, o fato não entra.
3. **Minuta** — gera só com pauta aprovada e dossiê "pronto para redação".
   Mostra corpo, SEO, textos sociais, fontes e ficha técnica da geração.
4. **Revisão** — verificação automática (sem modelo) ou revisão independente.
   Exibe veredito e problemas por severidade.
5. **Decisão** — aprovar ou rejeitar. Problema alto ou crítico aparece em
   vermelho, mas a aprovação segue permitida; veredito `bloqueado` impede.

Nenhuma etapa publica. Tudo fica no banco editorial local.

## 4. Comandos

```bash
# pipeline com pauta específica
/Users/rcorreas/miniconda3/envs/fla10/bin/python main.py "Flamengo x Palmeiras — destaques"

# pipeline com a pauta padrão (último jogo)
/Users/rcorreas/miniconda3/envs/fla10/bin/python main.py

# interface local
/Users/rcorreas/miniconda3/envs/fla10/bin/streamlit run app.py

# conferir a decisão da rotina sem executar nada
/Users/rcorreas/miniconda3/envs/fla10/bin/python rotina_pos_jogo.py --sem-executar

# fluxo por pauta, sem interface
.venv/bin/fla10 pipeline run --event-days 20
.venv/bin/fla10 pautas list --status awaiting_human
.venv/bin/fla10 pautas approve <proposta>
.venv/bin/fla10 dossie build <proposta>
.venv/bin/fla10 dossie mostrar <proposta>
.venv/bin/fla10 redacao gerar <proposta>
.venv/bin/fla10 redacao list
.venv/bin/fla10 redacao revisar <minuta>
.venv/bin/fla10 redacao aprovar <minuta>

# montar o pacote de uma versão já aprovada, sem interface
.venv/bin/python -m fla10_agents publicacao importar \
  exports/redacao-2026-11-10-1622 --versao 1
```

Cada execução grava em `exports/redacao-<data>-<hora>/`:

- `completa.md` — saída bruta do Revisor;
- `versao-1.md` a `versao-4.md` — versões separadas;
- `pauta.txt` — pauta usada, para a interface e a importação.

Depois da aprovação: `aprovada.json` na pasta da execução e o pacote em
`exports/pacotes/<execução>-v<versão>/`.

## 5. Aprovação

Só a interface grava `aprovada.json`. O arquivo guarda a versão escolhida e o
`conteudo_sha256` do texto sem espaços nas pontas. A importação recusa texto
alterado depois da aprovação e recusa pacote já publicado.

A verificação automática (`qualidade.py`) bloqueia a aprovação apenas em erro
estrutural: versão sem título `# ` ou marcador de versão vazado. Os demais
achados ficam como aviso:

- texto curto (menos de 400 caracteres);
- negrito `**` ou bloco de código não fechado;
- expressão "não encontrado" no corpo;
- duas versões com mais de 90% de vocabulário em comum;
- quantidade diferente de quatro versões.

## 6. Rotinas no OpenBot

Uma rotina ativa, no fuso `America/Sao_Paulo`:

| Horário | Papel |
|---|---|
| 07:00 | gera as propostas de pauta da agenda (`pipeline run --event-days 30`) e avisa só quando cria alguma |

Regras da rotina de pesquisa:

- janela de 30 dias: a proposta nasce quando o jogo entra na agenda, com
  antecedência para dossiê e minuta;
- não chama modelo e não consome cota — é leitura de banco e vault;
- dedupe por evento: rodar de novo atualiza sem duplicar e preserva a decisão
  humana já registrada;
- sem proposta nova, responde `routine_no_update` e não notifica;
- nunca aprova pauta, nunca publica.

As duas rotinas pós-jogo (23:30 e 08:00) foram **desativadas** quando o escopo
passou a ser pesquisa e minuta. Elas continuam cadastradas e podem ser
reativadas se as quatro versões voltarem ao fluxo.

Agendamento só no OpenBot. Não usar cron, `launchd` ou agendador do provedor: o
usuário não conseguiria ver nem parar o trabalho.

## 7. Publicação (manual — fora do escopo inicial)

> Fora do escopo inicial: a entrega é pesquisa e minuta. Esta seção fica
> documentada para quando a publicação for ativada, mas nenhuma etapa abaixo
> faz parte do fluxo de hoje.

O site lê a coleção `news` do Firestore. Não existe endpoint autorizado para
escrita e o formulário do painel exige URL de imagem 16:9. Por isso a
publicação é manual:

1. Abrir o painel de matérias do site.
2. Copiar título, subtítulo, conteúdo e SEO de `site-news.json`.
3. Informar a URL da imagem de capa.
4. Conferir a subcategoria sugerida (Profissional, Feminino ou Base).
5. Publicar pelo painel.

`site-news.json` já vem com `status: draft`, `image` vazia, `author` vazio e
`publishedAt` nulo. O campo `pendencias` lista o que falta preencher. Nada é
gravado no Firestore pelo sistema.

## 8. Limites conhecidos

- A cota gratuita do OpenCode esgota por janela. Quando isso acontece, o
  runtime responde `FreeUsageLimitError` (429) e a rotina registra a falha; a
  execução das 08:00 cobre o caso.
- O motor depende do runtime local do OpenCode estar instalado e autenticado.
  Não há fallback pago nem OpenRouter.
- A ficha do jogo e a consulta fixa de escalação só entram quando a pauta cita
  o adversário ou pede resultado/placar; isso evita contaminar pauta de outro
  assunto.
- A qualidade factual depende da apuração; o sistema não inventa dado ausente.
- O título deve começar com `# ` ou `## `; o prompt pede `# ` e o verificador
  aceita os dois níveis.
- O HTML do artigo usa `<br><br>` e `<h3>`; o `RichTextRenderer` do site procura
  `<p>` para inserir anúncio no meio. O texto é exibido; o posicionamento do
  anúncio pode variar.
- A renderização visual no navegador não foi conferida nesta entrega.
- O `fla10 redacao aprovar` só recusa texto com veredito `bloqueado`; um
  relatório `ajustes_necessarios` (inclusive issue de severidade alta) não
  impede a aprovação. A decisão é do editor — o painel mostra o aviso em
  vermelho, mas não bloqueia.
- O dossiê automático usa os fatos confirmados da pauta e as fontes do evento
  na agenda. Afirmações adicionais só entram pelo `dossie build --claims`; o
  painel não tem campo para colar afirmações.

## 9. Quando algo falha

| Sintoma | Causa provável | Ação |
|---|---|---|
| 429 `FreeUsageLimitError` | cota gratuita esgotada | esperar a janela e rodar de novo; a rotina das 08:00 cobre |
| `sem_dados` | API do Cartola indisponível | tentar de novo mais tarde; conferir a rede |
| `sem_jogo_recente` | nenhum jogo nas últimas 14 h | comportamento esperado |
| `ja_gerado` | o mesmo jogo já foi redigido | conferir `exports/.ultima-rotina.json` |
| menos de 4 versões | Revisor não marcou tudo | ler `completa.md`; não aprovar |
| pacote recusado | texto alterado ou versão errada | refazer a aprovação na interface |
| interface sem execuções | `exports/` vazia ou `FLA10_EXPORTS` errado | conferir a variável e a pasta |

## 10. Verificação da entrega

```bash
# suíte, lint e tipos
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/mypy src
```

Resultado esperado: 226 testes aprovados, Ruff sem achados e mypy sem erros em
`src`. O pipeline real foi executado ponta a ponta nesta entrega, com 6 tarefas
e 4 versões, a custo zero, em duas pautas diferentes (uma de bastidores, sem
ficha de partida, e uma de final da Copa do Brasil Feminina).

## 11. Linha canônica do repositório

**Decisão (10/11/2026): a linha local é a canônica.** O `origin/main` segue como
linha separada, sem mescla.

Motivos, com evidência da tentativa de mescla abortada:

- A linha remota não tem o pipeline: faltam `main.py`, `app.py`, `opencode_llm.py`,
  `versoes.py`, `resultados.py`, `pauta.py`, `qualidade.py`, `rotina_pos_jogo.py`
  e `requirements-pipeline.txt`. Sem ela não há o produto desta entrega.
- A linha remota define `OpenRouterSettings` com `openai/gpt-6-luna-pro` e
  `openai/gpt-6-luna` e exige `OPENROUTER_API_KEY`. Isso contradiz a regra do
  projeto: só `opencode/deepseek-v4.1-flash-free`, custo zero.
- Os conflitos são arquitetônicos, não textuais: `ReviewIssue` e `ReviewReport`
  existem nos dois lados com schemas diferentes (severidade `critico/alto` de um
  lado, `critical/high` do outro), `DraftArticle` de um lado e `ArticleDraft` do
  outro, e `EditorialRepository` em `editorial.store` de um lado e
  `editorial.repository` do outro. Resolver exigiria renomear modelos e refazer
  os dois conjuntos de testes.
- `calendar/cbf_source.py` diverge em comportamento: a linha local aceita rodada
  sem data como `provisional`; a remota lança `CBFSourceError` quando não acha a
  data. São regras opostas, e cada lado tem teste da própria regra.

O que já está mapeado para reaproveitar depois, por cherry-pick e não por mescla:
proteção contra redirecionamento interno no RSS
(`079bc29`, `32cf582`, `fca9b11`), deduplicação de sinais (`7faf326`) e o
planejador de cobertura da agenda (`ca2448e`, `dc5eb51`). Nada disso entra sem
um teste próprio no lado local.

Como os dois lados nasceram do mesmo ponto (`c2a0e92`), publicar a linha local
exige escolher entre criar uma branch nova no remoto ou substituir o
`origin/main`. Nenhum dos dois foi feito no `rcorreas/Fla10-Agents`.

### Destino da publicação

A linha local foi publicada em **`https://github.com/fladez/fla10-redacao`**
(branch `main`, commit `027790d`, 89 arquivos, repositório público). O CI
(`tests`) passou: https://github.com/fladez/fla10-redacao/actions/runs/42947189316

- `origin` → `fladez/fla10-redacao` (push).
- `fla10-agents-errado` → `rcorreas/Fla10-Agents` (guardado, sem uso).
- O clone em `Documents/Projetos/Fla10-Agents-oficial` segue com a outra linha;
  nada foi mesclado nem alterado lá.
- O token usado para o push fica no cofre do OpenBot, nunca no chat nem no
  repositório.
