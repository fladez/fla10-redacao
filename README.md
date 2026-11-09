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
Fundação técnica e módulo inicial de avaliação comparativa implementados. Lint e testes anteriores aprovados em Python 3.11 e 3.12; a nova implementação de avaliação aguarda execução da CI. A comparação real dos modelos depende da configuração segura da chave OpenRouter. Os agentes editoriais completos, parser de pautas e publicação automática ainda não estão implementados.
