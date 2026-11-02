# Arquitetura do sistema

## 1. Camadas
- **Controle:** recebe solicitações, apresenta estados e coleta aprovações.
- **Orquestração:** decompõe objetivos, define dependências e encaminha tarefas.
- **Agentes:** executam funções delimitadas e retornam resultados estruturados.
- **Serviços compartilhados:** busca, validação, políticas, registro e observabilidade.
- **Persistência:** tarefas, execuções, evidências, decisões e histórico.
- **Adaptadores:** conectam APIs e sistemas externos sem acoplar a lógica editorial ao fornecedor.

## 2. Comunicação
Usar contratos explícitos de entrada e saída. Uma tarefa registra identificador, objetivo, contexto, restrições, prazo, permissões, dependências e critério de conclusão. Uma entrega informa resultado, fontes, evidências, incertezas, limitações, artefatos e estado.

## 3. Coordenador
Deve decompor solicitações, selecionar agentes e ferramentas, controlar dependências e tentativas, impedir execução sem pré-requisitos, consolidar resultados preservando divergências e encaminhar decisões ao humano. Não substitui a revisão independente nem aprova publicação.

## 4. Persistência
SQLite no protótipo pode armazenar tarefas, execuções, fontes, evidências, aprovações e eventos. Usar identificadores estáveis e datas UTC. Planejar migração para PostgreSQL se a operação exigir concorrência ou escala.

## 5. Integrações
Cada integração terá adaptador, limites de uso, tratamento de falhas e testes. Fontes possíveis: calendários oficiais, sites, feeds, APIs esportivas, GitHub, CMS e ferramentas analíticas. Validar termos e estabilidade antes de automatizar coleta.

## 6. Tecnologia
Python é a base inicial. O OpenAI Agents SDK é candidato, sujeito a validação com documentação atual, segurança, custos e testes. Encapsular o framework para evitar dependência espalhada pela aplicação.

## 7. Observabilidade
Registrar tarefa, agente, versão das instruções, ferramentas, duração, estado, fontes, artefatos, erros, tentativas, decisões, aprovações e ações externas realizadas. Nunca registrar segredos ou dados pessoais desnecessários.

## 8. Princípios de implementação
Módulos pequenos; contratos tipados; configuração separada; operações idempotentes quando possível; timeout e retry limitados; testes unitários e de integração; modo simulado para ações de risco; estado global independente de qualquer agente.
