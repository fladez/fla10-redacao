# Plano de implantação

## Fase 0 — Fundação documental e integração
**Entregas:** documento fundador, arquitetura, agentes, fluxo, segurança, integração com Redacao-Fla10, fluxo MVP e contratos de dados.

**Estado:** documentação inicial criada e integração editorial mapeada. Falta validar a leitura automatizada do vault com credencial de somente leitura e testar a extração de pautas em amostra.

## Fase 1 — MVP de pesquisa e apuração
Implementar Calendário e Agenda, Monitoramento e Pautas, e Apuração e Verificação.

Capacidades:
- leitura somente de fontes autorizadas e do Redacao-Fla10;
- normalização de eventos;
- detecção de mudanças no calendário;
- identificação de fatos novos;
- comparação com pautas publicadas, reservadas e canceladas;
- propostas de pauta com pergunta e ângulo próprios;
- dossiês com afirmações, evidências, fontes, contradições e lacunas;
- persistência, versionamento e logs.

Fora do escopo: redação integral, publicação automática, alteração do Redacao-Fla10, distribuição automática e decisões editoriais sem aprovação.

### Sequência de implementação
1. Ambiente Python, configuração e testes.
2. Adaptador GitHub somente leitura e parser de documentos editoriais.
3. Modelos de dados e persistência SQLite.
4. Adaptador inicial de calendário para uma fonte oficial prioritária.
5. Agente Calendário e Agenda.
6. Agente Monitoramento e Pautas, incluindo detecção de redundância.
7. Agente Apuração e Verificação.
8. Orquestração do fluxo e avaliação com casos reais.

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
Preparar o esqueleto Python, validar a autenticação de leitura do GitHub e implementar primeiro o adaptador editorial. Só depois iniciar a coleta automatizada de calendários.
