# Fla10-Agents

Sistema modular de agentes especializados para apoiar a Redação Fla10.

## Objetivo
Apoiar monitoramento, planejamento, apuração, produção, revisão, SEO, distribuição e registro editorial, mantendo a decisão final e a autorização de publicação sob responsabilidade humana.

## Repositórios
- **Fla10-Agents:** código, arquitetura, orquestração, integrações, testes e documentação técnica.
- **Redacao-Fla10:** fonte canônica das regras editoriais, formatos, pautas, agenda, processos e histórico.

O sistema consulta as regras do Redacao-Fla10 em modo somente leitura. Não cria uma cópia concorrente nem altera esse repositório.

## Princípios
1. Autonomia operacional com autoridade editorial humana.
2. Fontes rastreáveis; distinção entre fato, relato, análise e hipótese.
3. Agentes especializados com responsabilidades e permissões delimitadas.
4. Revisão independente da produção.
5. Ações externas somente com autorização e confirmação verificável.
6. Estado editorial separado do estado técnico das execuções.
7. Desenvolvimento incremental, testável e reversível.

## MVP
Calendário e Agenda, Monitoramento e Pautas, Apuração e Verificação, Produção, Revisão e preparação de publicação assistida. O sistema identifica eventos e fatos novos, compara com a memória editorial, recomenda pautas, prepara dossiês verificáveis, redige a partir de pauta aprovada e dossiê suficiente, revisa o texto de forma independente e monta o pacote de CMS. Aprovação e publicação continuam sob controle humano; nenhum conteúdo é enviado ao site automaticamente.

## Documentação
- [Documento fundador](docs/01-documento-fundador.md)
- [Arquitetura](docs/02-arquitetura.md)
- [Agentes e responsabilidades](docs/03-agentes-e-responsabilidades.md)
- [Fluxo operacional](docs/04-fluxo-operacional.md)
- [Segurança e permissões](docs/05-seguranca-e-permissoes.md)
- [Plano de implantação](docs/06-plano-de-implantacao.md)
- [Integração com Redacao-Fla10](docs/07-integracao-com-redacao-fla10.md)
- [Fluxo MVP ponta a ponta](docs/08-fluxo-mvp-ponta-a-ponta.md)
- [Contratos de dados do MVP](docs/09-contratos-de-dados-mvp.md)
- [Configuração local](docs/10-configuracao-local.md)
- [Protocolo de avaliação comparativa](docs/11-protocolo-avaliacao-modelos.md)
- [Prompt comum do teste de reportagem](docs/12-prompt-comum-teste-reportagem.md)
- [Pacote documental — A força da Nação](docs/13-caso-teste-a-forca-da-nacao.md)

## Diagnóstico da integração editorial

Depois de configurar o arquivo local `.env`:

```bash
fla10 check-editorial
```

O comando confirma a leitura dos quatro documentos-base e informa o commit consultado. Não altera o repositório editorial.

## Avaliação comparativa de modelos

O primeiro caso editorial está preparado. Depois de configurar `OPENROUTER_API_KEY` localmente:

```bash
fla10 run-report-test
```

O comando envia o mesmo prompt e o mesmo dossiê aos três modelos definidos no protocolo, salva as respostas cegas e os metadados em `artifacts/model-evaluation/`, diretório ignorado pelo Git. A chave de identificação dos modelos fica em arquivo separado nessa pasta. Não compartilhe a chave de API nem publique os resultados antes da avaliação.

A execução real ainda depende de configurar a chave e validar a primeira rodada. Consulte [Configuração local](docs/10-configuracao-local.md).

## Estado
Fundação técnica, avaliação comparativa, calendário esportivo e Fases 1, 2 e 3 do MVP implementados localmente. Ruff, mypy e a suíte de testes passam em Python 3.11 e 3.12. A comparação paga de modelos continua pendente de decisão do responsável; o modelo provisório de redação é `openai/gpt-5.5`. A publicação ainda não envia conteúdo ao site: o sistema prepara o pacote CMS, exporta arquivos locais e só registra uma matéria como publicada após URL e confirmação verificável. A publicação automática depende de um endpoint autorizado no site.


## Calendário esportivo — operação local inicial

O calendário já pode receber observações normalizadas em JSON e manter os eventos e o histórico em SQLite. Esta etapa permite operar e validar o agente sem depender de um coletor externo ainda não implementado.

Exemplo de arquivo `evento.json`:

```json
{
  "provider": "cbf",
  "external_id": "identificador-na-fonte",
  "event": {
    "sport": "futebol",
    "category": "profissional masculino",
    "competition": "Campeonato Brasileiro",
    "season": "2026",
    "stage": "rodada 33",
    "home_team": "Flamengo",
    "away_team": "Palmeiras",
    "starts_at_local": "2026-11-10T19:00:00",
    "timezone": "America/Sao_Paulo",
    "venue": "Maracanã",
    "event_status": "confirmed",
    "sources": [],
    "last_verified_at": "2026-11-10T12:00:00Z"
  }
}
```

Processar e atualizar o banco local:

```bash
fla10 calendar process --input evento.json
```

Consultar os eventos registrados:

```bash
fla10 calendar list
```

O comando não busca fontes na internet nem inventa dados ausentes. O arquivo deve conter informações já apuradas; cada execução preserva o histórico de alterações. Uma observação recusada por conflito de identidade não altera o banco e faz o comando terminar com código 1. O banco padrão fica em `data/calendar.db` e pode ser alterado com `--database`.

### Importação de jogos pela tabela oficial da CBF

Para competições cobertas pela CBF, o calendário pode importar partidas do Flamengo diretamente de um PDF oficial de tabela detalhada. O importador preserva o número de referência do jogo como identificador externo e registra o endereço do documento como fonte de evidência.

Comando:

```bash
fla10 calendar sync-cbf --url "URL_DO_PDF_OFICIAL_DA_CBF" --season 2026
```

A URL deve apontar para o PDF publicado pela CBF (por exemplo, o anexo "Tabela Detalhada - Brasileiro Série A 2026"). A cada nova tabela ou retificação, execute novamente o comando com a URL atualizada. O agente identifica jogos já importados pelo código oficial e atualiza alterações sem duplicar eventos.

Nesta primeira integração, o importador cobre somente jogos do Flamengo na tabela detalhada do Campeonato Brasileiro Série A. Não importa outras equipes, competições ou modalidades. Se o PDF não puder ser interpretado ou não contiver jogos do Flamengo, a execução falha sem gravar eventos.

O identificador externo é prefixado pela temporada (`2026:368`), o que evita colisão entre anos. A importação roda em uma única transação: se um jogo falhar no meio do processo, nada é gravado. Jogos recusados por conflito de identidade aparecem no resultado e fazem o comando terminar com código 1.

Os documentos oficiais ficam em [Tabelas da Série A](https://www.cbf.com.br/futebol-brasileiro/tabelas/campeonato-brasileiro/serie-a/2026?documento=Tabela%20Detalhada). Rodadas ainda sem data marcada entram como `provisional`, com `starts_at_local` nulo; o horário nunca é estimado. O campo `venue` traz estádio, cidade e UF como publicados na tabela.

Uma tabela real de 09/11/2026, com 11 páginas, foi lida de ponta a ponta: 38 jogos do Flamengo, 36 confirmados e 2 sem data, sem duplicar eventos na segunda execução.

Consultar o histórico de importações:

```bash
fla10 calendar runs --limit 10
```

Cada execução registra provedor, URL do PDF, início, fim, status e a contagem de eventos criados, atualizados, inalterados e recusados.

O banco padrão é `data/calendar.db` na raiz do projeto, independentemente da pasta em que o comando é executado. Para usar outro arquivo, informe `--database` ou defina `FLA10_DATABASE`.

O banco usa WAL e timeout de bloqueio, o que permite leitura simultânea por outros processos. O schema tem versão (`PRAGMA user_version`); abrir um banco criado por uma versão mais nova falha com mensagem explícita.

## Monitoramento, pautas e apuração — Fase 1

A Fase 1 lê o vault editorial local em modo somente leitura, cruza agenda e sinais de monitoramento, propõe pautas, aponta redundância e monta dossiês de apuração. Nenhuma proposta é aprovada e nenhum texto é publicado automaticamente.

### Configuração

- `EDITORIAL_VAULT_PATH`: raiz do vault. Padrão: `~/Documents/Redacao-Fla10`.
- `FLA10_EDITORIAL_DATABASE`: banco do estado editorial. Padrão: `data/editorial.db` na raiz do projeto.
- `FLA10_DATABASE`: banco do calendário. Padrão: `data/calendar.db` na raiz do projeto.

O vault não é alterado. Pautas, sinais, dossiês e decisões ficam apenas no banco editorial local.

### Consultar o vault e as pautas

```bash
fla10 vault status
fla10 pautas parse
```

`vault status` mostra o commit lido, os documentos carregados e a contagem de pautas por tipo. `pautas parse` extrai títulos, estado, janela, foco e checagens das notas, sem gravar nada. Pautas repetidas entre o painel e o registro de reservas são contadas uma única vez.

### Alimentar sinais de monitoramento

O arquivo de entrada deve conter uma lista de sinais ou um objeto com a chave `signals`:

```json
{
  "signals": [
    {
      "provider": "rss",
      "external_id": "noticia-123",
      "title": "Flamengo confirma retorno de jogador",
      "summary": "Atleta voltou aos treinos com o grupo.",
      "url": "https://exemplo.com/noticia",
      "published_at": "2026-11-10T12:00:00-03:00",
      "teams": ["Flamengo"],
      "topics": ["treino"],
      "players": []
    }
  ]
}
```

```bash
fla10 sinais add --input sinais.json --provider rss
fla10 sinais list --limit 20
```

O provedor pode vir no arquivo ou ser fixado com `--provider`. A combinação provedor + identificador externo evita duplicatas: um sinal repetido atualiza o conteúdo e a data de última observação, sem criar outra linha. Datas precisam incluir fuso horário.

### Gerar e decidir propostas de pauta

```bash
fla10 pipeline run --event-days 7 --signal-days 3
fla10 pautas list --status awaiting_human
fla10 pautas approve ID_DA_PROPOSTA
fla10 pautas reject ID_DA_PROPOSTA
```

O pipeline combina:

- jogos do Flamengo na janela de `--event-days` para propostas de serviço;
- sinais recentes que mencionem o Flamengo na janela de `--signal-days` para propostas de última notícia;
- pautas do vault e matérias já publicadas para a checagem de redundância.

Cada proposta registra pergunta editorial, ângulo, fatos confirmados, informações a verificar, fontes iniciais, janela, prioridade e risco de redundância. A deduplicação usa o evento ou o sinal de origem; executar o pipeline de novo atualiza o conteúdo sem duplicar propostas e preserva a decisão humana já registrada.

A aprovação é sempre humana. `approve` e `reject` apenas registram a decisão no banco; o vault não é alterado.

### Montar o dossiê de apuração

O dossiê só é montado para proposta com decisão `approved`. Uma proposta pendente ou rejeitada retorna erro sem gravar dossiê.

```bash
fla10 dossie build ID_DA_PROPOSTA --claims claims.json --contradiction "Horário divergente em fonte secundária."
```

Formato de `claims.json`:

```json
{
  "claims": [
    {
      "claim_id": "c1",
      "claim_text": "O jogo está marcado para 12 de novembro de 2026.",
      "classification": "confirmed",
      "evidence": [
        {
          "url": "https://exemplo.com/tabela",
          "source_type": "tabela oficial",
          "author_or_institution": "CBF",
          "accessed_at": "2026-11-10T10:00:00-03:00",
          "supports": ["data"]
        }
      ]
    }
  ]
}
```

Classificações aceitas: `confirmed`, `attributed`, `context`, `analysis`, `hypothesis` e `unconfirmed`. O dossiê separa fatos utilizáveis, informações que exigem atribuição, análise admissível e afirmações excluídas. Fato confirmado sem evidência e atribuição sem autor identificado viram lacunas críticas. O resultado recomenda `pronto para redação`, `revisar contradições` ou `apuração insuficiente`.

### Registrar matérias publicadas

```bash
fla10 publicacoes add --title "Flamengo x Palmeiras: onde assistir" --url "https://exemplo.com/materia" --published-at "2026-11-11T10:00:00-03:00"
fla10 publicacoes list
```

Esse registro alimenta a comparação de redundância. A data de publicação precisa incluir fuso horário. O comando não publica nada: apenas registra uma matéria que já saiu.

### Limites desta fase

- Não redige matérias completas.
- Não altera o vault nem o painel de pautas.
- Não publica, não envia e não agenda conteúdo externo.
- A nota de redundância é uma triagem por sobreposição de termos; a decisão continua humana.
- Sinais de monitoramento ainda são ingeridos por arquivo JSON; não há coletor de fontes nesta fase.

## Produção, revisão e publicação assistida — Fases 2 e 3

As fases 2 e 3 geram texto a partir de pauta aprovada e dossiê com recomendação `pronto para redação`, aplicam revisão independente e preparam o pacote de CMS. Nenhuma etapa publica sozinha.

### Configuração do provedor

- `OPENROUTER_API_KEY`: obrigatória para gerar e revisar com modelo.
- `OPENROUTER_API_URL`: padrão `https://openrouter.ai/api/v1`.
- `FLA10_WRITING_MODEL`: modelo de redação. Padrão provisório: `openai/gpt-5.5`.
- `FLA10_REVIEW_MODEL`: modelo revisor. Quando ausente, usa o modelo de redação.

A chamada não permite fallback silencioso: se o modelo configurado falhar, o comando interrompe. A chave nunca é exibida em mensagens de erro ou logs.

### Fluxo completo

```bash
# 1. Aprovar a pauta (decisão humana já registrada na Fase 1)
fla10 pautas approve ID_DA_PROPOSTA

# 2. Gerar o texto
fla10 redacao gerar ID_DA_PROPOSTA

# 3. Revisar de forma independente
fla10 redacao revisar ID_DO_TEXTO
# ou, sem chamada de modelo:
fla10 redacao revisar ID_DO_TEXTO --deterministico

# 4. Consultar e decidir
fla10 redacao list
fla10 redacao mostrar ID_DO_TEXTO
fla10 redacao aprovar ID_DO_TEXTO
fla10 redacao rejeitar ID_DO_TEXTO

# 5. Preparar e exportar o pacote local
fla10 publicacao preparar ID_DO_TEXTO
fla10 publicacao exportar ID_DO_PACOTE --output exports/

# 6. Só após publicar manualmente no site, registrar a URL confirmada
fla10 publicacao registrar ID_DO_PACOTE \
  --url "https://fla10.news/materia" \
  --published-at "2026-11-10T18:00:00-03:00" \
  --confirmar "Confirmado no painel do site"
```

A geração exige pauta `approved` e dossiê `pronto para redação`. O texto nasce como `awaiting_human`; a aprovação é bloqueada enquanto a revisão mais recente for `bloqueado`. `ajustes_necessarios` e `pronto_para_avaliacao_humana` exigem leitura do editor, mas não impedem a decisão humana.

A exportação cria uma subpasta por pacote com `article.html`, `article.md`, `package.json` e `metadata.json`. O registro de publicação grava também o título em `published_articles` para alimentar a checagem de redundância. Não há envio de conteúdo, chamada de CMS ou agendamento externo.

### Vereditos da revisão

- `bloqueado`: problema crítico; aprovação impedida.
- `ajustes_necessarios`: problema alto ou médio que exige correção.
- `pronto_para_avaliacao_humana`: sem achados que impeçam a leitura final.

A revisão combina checagens determinísticas (campos obrigatórios, marcadores, URLs no corpo e checklist do formato) com análise por modelo. O revisor não reescreve o texto: aponta problemas e evidências.

### Limites das fases 2 e 3

- O modelo padrão é provisório até a avaliação comparativa ser executada.
- A qualidade factual depende do dossiê; o sistema não busca fontes sozinho na geração.
- A publicação externa continua manual: não existe endpoint autorizado no site.
- O registro de publicação exige URL e confirmação verificável; sem isso, o pacote permanece `exported`.
