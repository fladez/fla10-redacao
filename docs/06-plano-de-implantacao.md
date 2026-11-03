# Plano de implantação

## Fase 0 — Fundação documental e integração
**Entregas:** documento fundador, arquitetura, agentes, fluxo, segurança, integração com Redacao-Fla10, fluxo MVP e contratos de dados.

**Estado:** documentação inicial criada e mapeada contra os arquivos reais do vault. O esqueleto Python, adaptador GitHub somente leitura, modelos de dados, comando de diagnóstico, testes iniciais e workflow de CI foram adicionados. Lint e testes passaram em Python 3.11 e 3.12 no GitHub Actions. A conexão real ainda depende da credencial de leitura criada e configurada pelo responsável.

## Fase 1 — MVP de pesquisa e apuração
Implementar Calendário e Agenda, Monitoramento e Pautas, e Apuração e Verificação.

Capacidades: leitura somente de fontes autorizadas e do Redacao-Fla10; normalização de eventos; detecção de mudanças; identificação de fatos novos; comparação com pautas publicadas, reservadas e canceladas; propostas de pauta com ângulo próprio; dossiês rastreáveis; persistência e logs.

Fora do escopo: redação integral, publicação automática, alteração do Redacao-Fla10, distribuição automática e decisões editoriais sem aprovação.

### Sequência de implementação
1. **Base criada e validada:** ambiente Python, configuração, CLI, lint e testes iniciais.
2. **Base criada:** adaptador GitHub somente leitura e mapa de documentos editoriais.
3. **Próxima implementação:** conexão real ao vault, seguida de persistência SQLite e parser do Painel de Pautas/Projetos Reservados.
4. Adaptador inicial de calendário para uma fonte oficial prioritária.
5. Agente Calendário e Agenda.
6. Agente Monitoramento e Pautas, incluindo detecção de redundância.
7. Agente Apuração e Verificação.
8. Orquestração e avaliação com casos reais.

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
Criar a credencial GitHub somente leitura no ambiente local, clonar o repositório e executar `fla10 check-editorial`. Depois da conexão real validada, implementar o parser do painel de pautas e a persistência SQLite.
