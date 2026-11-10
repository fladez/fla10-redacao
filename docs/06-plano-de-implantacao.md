# Plano de implantação

## Fase 0 — Fundação documental e integração
**Entregas:** documento fundador, arquitetura, agentes, fluxo, segurança, integração com Redacao-Fla10, fluxo MVP e contratos de dados.

**Estado:** documentação inicial criada e mapeada contra os arquivos reais do vault. O esqueleto Python, adaptador GitHub somente leitura, modelos de dados, comando de diagnóstico, testes iniciais e workflow de CI foram adicionados. Lint e testes passaram em Python 3.11 e 3.12 no GitHub Actions. A conexão real ainda depende da credencial de leitura criada e configurada pelo responsável.

## Fase 1 — MVP de pesquisa e apuração
Implementar Calendário e Agenda, Monitoramento e Pautas, e Apuração e Verificação.

Capacidades: leitura somente de fontes autorizadas e do Redacao-Fla10; normalização de eventos; detecção de mudanças; identificação de fatos novos; comparação com pautas publicadas, reservadas e canceladas; propostas de pauta com ângulo próprio; dossiês rastreáveis; persistência e logs.

Fora do escopo: redação integral, publicação automática, alteração do Redacao-Fla10, distribuição automática e decisões editoriais sem aprovação.

**Estado:** implementada em modo local. O sistema lê o vault por caminho local em somente leitura, importa a tabela oficial da CBF, mantém calendário e estado editorial em SQLite, extrai pautas do painel, gera propostas a partir de jogos e sinais, sinaliza redundância, registra decisões humanas e monta dossiês de apuração. A operação real ainda depende de alimentar sinais de monitoramento e de revisar as propostas com o editor.

### Sequência de implementação
1. **Concluído:** ambiente Python, configuração, CLI, lint e testes iniciais.
2. **Concluído:** adaptador GitHub somente leitura e mapa de documentos editoriais.
3. **Concluído:** conexão real ao vault local, persistência SQLite e parser do Painel de Pautas/Projetos Reservados.
4. **Concluído:** importador da tabela detalhada da CBF para jogos do Flamengo.
5. **Concluído:** agente Calendário e Agenda, com identidade, merge por campo e histórico de execuções.
6. **Concluído:** agente Monitoramento e Pautas, com ingestão de sinais, deduplicação e detecção de redundância.
7. **Concluído:** agente Apuração e Verificação, com dossiê, lacunas, contradições e recomendação.
8. **Concluído:** orquestração ponta a ponta coberta por testes, com casos sintéticos e banco temporário.
9. **Concluído:** produção, revisão independente e decisão humana (Fase 2), com motor gratuito DeepSeek V4.1 Flash Free pelo OpenCode e revisão determinística disponível.
10. **Concluído:** pacote de CMS, exportação local e registro de publicação confirmada (Fase 3), sem envio externo.
11. **Suspenso:** avaliação comparativa paga. O motor gratuito DeepSeek V4.1 Flash Free é o padrão inicial; a comparação só roda com `FLA10_ENABLE_PAID_EVALUATION=1`.

## Fase 2 — Produção e revisão
Adicionar Produção e Revisão independente. Testar formatos Fla10, validar HTML e marcadores obrigatórios e medir retrabalho com casos reais.

**Estado:** implementada em modo local. A produção usa o motor gratuito DeepSeek V4.1 Flash Free pelo runtime local do OpenCode, lê os documentos canônicos do vault e só gera a partir de pauta `approved` e dossiê `pronto para redação`. A revisão combina checagens determinísticas e análise por modelo independente; a aprovação humana é bloqueada quando o parecer mais recente é `bloqueado`. O modelo padrão é `opencode/deepseek-v4.1-flash-free`, configurável por `FLA10_WRITING_MODEL` e `FLA10_REVIEW_MODEL`. A avaliação comparativa paga está desativada por padrão.

## Fase 3 — SEO, distribuição e publicação assistida
Adicionar metadados, adaptações de distribuição e preparação de CMS. Manter aprovação humana para toda ação pública.

**Estado:** implementada como publicação assistida. O sistema monta pacote de CMS com título, subtítulo, HTML, Markdown, resumo para IA, pacote SEO, textos sociais e fontes; exporta `article.html`, `article.md`, `package.json` e `metadata.json` para uma pasta local; e só registra a matéria como publicada após URL válida, data com fuso e confirmação verificável. Não envia conteúdo ao site, não chama API de CMS e não agenda publicação externa.

## Fase 4 — Auditoria e autonomia progressiva
Adicionar auditoria contínua e métricas. Aumentar autonomia somente com evidência de confiabilidade, aprovação e controles de reversão.

## Critérios de aceite
Requisitos testáveis; testes automatizados passando; fontes rastreáveis; incertezas explícitas; permissões verificadas; logs suficientes para reconstruir execução; avaliação humana favorável.

## Métricas iniciais
Precisão de datas e fatos; proporção de afirmações com evidência; uso de fontes primárias; contradições detectadas; falsos positivos e duplicidade; erros críticos; retrabalho; tempo/custo por tarefa; falhas de integração e violações de permissão.

## Próxima etapa
As fases 1, 2 e 3 estão operacionais localmente com o motor gratuito DeepSeek V4.1 Flash Free pelo OpenCode. A avaliação comparativa paga foi suspensa e só pode ser executada com autorização explícita. A publicação automática continua fora do escopo até existir um endpoint autorizado no site; por enquanto, o fluxo termina em exportação local e registro manual confirmado.
