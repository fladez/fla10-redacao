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
8. **Parcial:** orquestração ponta a ponta coberta por testes. Falta validar a operação com casos reais e decidir os modelos da Fase 2.

## Fase 2 — Produção e revisão
Adicionar Produção e Revisão independente. Testar formatos Fla10, validar HTML e marcadores obrigatórios e medir retrabalho com casos reais.

## Fase 3 — SEO, distribuição e publicação assistida
Adicionar metadados, adaptações de distribuição e preparação de CMS. Manter aprovação humana para toda ação pública.

## Fase 4 — Auditoria e autonomia progressiva
Adicionar auditoria contínua e métricas. Aumentar autonomia somente com evidência de confiabilidade, aprovação e controles de reversão.

## Critérios de aceite
Requisitos testáveis; testes automatizados passando; fontes rastreáveis; incertezas explícitas; permissões verificadas; logs suficientes para reconstruir execução; avaliação humana favorável.

## Métricas iniciais
Precisão de datas e fatos; proporção de afirmações com evidência; uso de fontes primárias; contradições detectadas; falsos positivos e duplicidade; erros críticos; retrabalho; tempo/custo por tarefa; falhas de integração e violações de permissão.

## Próxima etapa
A Fase 1 está operacional localmente. A Fase 2 depende de duas decisões do responsável: provedor/modelo de linguagem com chave configurada e formato de entrega para revisão humana. A publicação continua fora do escopo até existir um endpoint autorizado no site.
