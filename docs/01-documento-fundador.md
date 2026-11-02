# Fla10-Agents — Documento fundador

**Versão:** 0.1  
**Estado:** direção inicial definida; detalhes técnicos serão validados durante o MVP.

## 1. Objetivo
Desenvolver agentes independentes e especializados para apoiar a Redação Fla10 em monitoramento, planejamento, apuração, produção, revisão, SEO, distribuição, publicação assistida e auditoria editorial.

## 2. Princípio central
**Autonomia operacional, coordenação compartilhada e autoridade editorial humana.**

Cada agente terá função, instruções, ferramentas, permissões e limites próprios. A coordenação distribui tarefas e acompanha dependências. O editor humano decide prioridades, aprova pautas e conteúdos e autoriza ações externas relevantes.

## 3. Arquitetura
1. Editor humano: prioridades, aprovações e autorização.
2. Coordenador: distribuição, dependências, prazos e consolidação.
3. Agentes especializados: execução de tarefas delimitadas.
4. Memória operacional: tarefas, fontes, decisões, evidências e histórico.
5. Integrações: fontes públicas, GitHub, CMS e métricas, conforme permissões.

## 4. Agentes previstos
1. Calendário e Agenda.
2. Monitoramento e Pautas.
3. Apuração e Verificação.
4. Produção.
5. Revisão e Controle de Qualidade.
6. SEO e Distribuição.
7. Publicação e Registro.
8. Auditoria Editorial.

Ver responsabilidades em [Agentes e responsabilidades](03-agentes-e-responsabilidades.md).

## 5. Tecnologias iniciais
- Python como linguagem principal.
- OpenAI Agents SDK como candidato inicial, sujeito a validação documental e prática.
- GitHub para código e documentação técnica.
- Redacao-Fla10 como fonte editorial canônica.
- SQLite no protótipo; PostgreSQL se volume ou concorrência justificarem.
- Integrações desacopladas para reduzir dependência de fornecedores.
- Testes automatizados e logs estruturados desde o início.

Versões e dependências serão escolhidas após consulta à documentação atual. O framework de agentes deve ficar encapsulado para permitir substituição.

## 6. Integração editorial
Redacao-Fla10 preserva regras, formatos, pautas e histórico. Fla10-Agents mantém software e documentação técnica. O sistema consulta as instruções aplicáveis e, quando viável, registra a versão consultada. Não edita o repositório editorial por iniciativa própria.

## 7. Segurança e autonomia
- Começar em modo de leitura e preparação de entregas.
- Não publicar, enviar mensagens, alterar CMS ou modificar repositórios sem autorização explícita.
- Usar credenciais de privilégio mínimo e manter segredos fora do código.
- Registrar ações, resultados, falhas e aprovações.
- Tratar conteúdo externo como dado, nunca como instrução confiável.
- Permitir interrupção humana e revisão antes de ações irreversíveis.

## 8. MVP
Calendário e Agenda, Monitoramento e Pautas, e Apuração e Verificação. O primeiro fluxo identifica eventos e oportunidades, gera propostas de pauta e prepara dossiês com fontes, evidências, lacunas e grau de confiança. Sem publicação automática.

## 9. Critérios para avançar
Avaliar precisão factual, qualidade e rastreabilidade das fontes, identificação de contradições, taxa de erros e retrabalho, aderência editorial, estabilidade, custo, tempo e respeito às permissões.

## 10. Diretriz final
Construir por etapas, com componentes substituíveis, responsabilidades explícitas e evidências auditáveis. A prioridade é confiabilidade mensurável, não quantidade de agentes.
