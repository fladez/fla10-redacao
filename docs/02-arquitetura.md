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

## 4. Integração com a base editorial
O adaptador GitHub consulta `rcorreas/Redacao-Fla10` em modo somente leitura. Cada execução registra branch, commit SHA e caminhos consultados. O sistema carrega os documentos de entrada obrigatórios e, depois, apenas os manuais pertinentes à tarefa.

O cache local é derivado e identificado pelo commit de origem. Não é uma segunda base editorial. O Painel de Pautas e Projetos e Pautas Reservadas são interpretados como documentos históricos e operacionais, não como listas planas de itens atuais. Detalhes em [Integração com Redacao-Fla10](07-integracao-com-redacao-fla10.md).

## 5. Dois eixos de estado
O estado editorial segue o Redacao-Fla10; o estado operacional acompanha execução de tarefas no Fla10-Agents. São campos separados. Uma execução concluída não significa que a pauta foi aprovada ou publicada. No MVP, agentes não alteram estados no vault.

## 6. Persistência
SQLite no protótipo pode armazenar tarefas, execuções, fontes, evidências, aprovações e eventos. Usar identificadores estáveis e datas UTC. Planejar migração para PostgreSQL se a operação exigir concorrência ou escala.

## 7. Integrações externas
Cada integração terá adaptador, limites de uso, tratamento de falhas e testes. Fontes possíveis: calendários oficiais, sites, feeds, APIs esportivas, GitHub, CMS e ferramentas analíticas. Validar termos e estabilidade antes de automatizar coleta. O MVP usa leitura de fontes e não executa publicação ou escrita no vault.

## 8. Tecnologia
Python é a base inicial. O OpenAI Agents SDK é candidato, sujeito a validação com documentação atual, segurança, custos e testes. Encapsular o framework para evitar dependência espalhada pela aplicação.

## 9. Observabilidade
Registrar tarefa, agente, versão das instruções, ferramentas, duração, estado, fontes, commit do vault, artefatos, erros, tentativas, decisões, aprovações e ações externas realizadas. Nunca registrar segredos ou dados pessoais desnecessários.

## 10. Princípios de implementação
Módulos pequenos; contratos tipados; configuração separada; operações idempotentes quando possível; timeout e retry limitados; testes unitários e de integração; modo simulado para ações de risco; estado global independente de qualquer agente.
