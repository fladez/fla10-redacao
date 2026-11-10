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
Calendário e Agenda, Monitoramento e Pautas, e Apuração e Verificação. O MVP identifica eventos e fatos novos, compara com a memória editorial, recomenda pautas e prepara dossiês verificáveis. Não redige matérias completas, não altera o vault e não publica.

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
Fundação técnica, avaliação comparativa e importação de calendário implementadas. Ruff, mypy e a suíte de testes passam em Python 3.11 e 3.12. A comparação real dos modelos depende da configuração segura da chave OpenRouter. Os agentes editoriais completos, o parser de pautas e a publicação automática ainda não estão implementados.


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

O comando não busca fontes na internet nem inventa dados ausentes. O arquivo deve conter informações já apuradas; cada execução preserva o histórico de alterações. Uma observação recusada por conflito de identidade não altera o banco e faz o comando terminar com código 1. O banco padrão fica em `data/calendar.db` e pode ser alterado com `--database`.### Importação de jogos pela tabela oficial da CBF

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
