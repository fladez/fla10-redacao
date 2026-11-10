# Identidade e reconciliação de eventos esportivos

## 1. Objetivo

Definir como o Fla10-Agents identifica um evento esportivo ao receber
informações de diferentes fontes, evitando duplicidades e fusões indevidas.

## 2. Identidade interna

Cada evento possui um `event_id` interno, único e estável.

- Novos eventos recebem um UUID.
- O identificador é preservado durante toda a existência do evento.
- Alterações de data, horário, estádio, situação ou fontes não modificam
  o `event_id`.
- Identificadores fornecidos por fontes externas nunca substituem o
  identificador interno.

## 3. Identidade externa

Cada identificação externa é composta por:

- `provider`: identificação da fonte ou provedor;
- `external_id`: identificador do evento nessa fonte.

A combinação `(provider, external_id)` deve ser única.

Uma identificação externa já associada a um evento não pode ser
silenciosamente transferida para outro.

Quando a fonte reutiliza o mesmo código entre temporadas — caso da tabela
detalhada da CBF —, o `external_id` é prefixado pela temporada no formato
`temporada:código` (exemplo: `2026:368`). O prefixo evita que o código de
um jogo antigo seja confundido com o de outro jogo na temporada seguinte;
a importação de uma nova tabela atualiza o evento já vinculado em vez de
criar um duplicado.

## 4. Reconciliação de eventos

A resolução deve obedecer à seguinte prioridade:

1. Consultar identificadores externos já associados.
2. Verificar se os identificadores recebidos apontam para um único
   evento interno.
3. Na ausência de associação externa, procurar correspondência
   determinística entre eventos existentes.
4. Se houver exatamente um candidato compatível, associar a nova
   identificação externa ao evento existente.
5. Se houver mais de um candidato, classificar como ambíguo.
6. Se não houver candidato, permitir a criação de um novo evento.

## 5. Correspondência determinística

A comparação inicial considera:

- modalidade;
- categoria;
- competição;
- temporada;
- mandante;
- visitante.

A fase ou rodada é utilizada como elemento adicional de distinção.

A normalização inicial de textos pode desconsiderar diferenças de
maiúsculas, minúsculas e espaços excedentes.

Não serão presumidas equivalências entre nomes diferentes de clubes,
competições ou categorias sem um cadastro explícito de aliases.

Data, horário e estádio são atributos de confirmação e contexto,
não componentes da identidade permanente.

## 6. Ambiguidade e conflitos

O sistema não deve fundir automaticamente eventos quando:

- mais de um evento existente satisfizer os critérios;
- identificadores externos recebidos apontarem para eventos internos
  diferentes;
- um identificador externo conhecido apresentar dados esportivos
  incompatíveis com o evento associado.

Nesses casos, deve preservar os registros e sinalizar a necessidade
de revisão.

Não excluir, sobrescrever ou fundir eventos como tentativa automática
de resolver conflitos.

## 7. Alterações do evento

Uma remarcação ou alteração de horário, estádio ou situação não cria
uma nova identidade.

O evento mantém seu `event_id`, e as diferenças relevantes devem
ser registradas no histórico.

## 8. Limites da primeira versão

A primeira implementação utilizará regras determinísticas.

Ficam fora do escopo:

- correspondência probabilística;
- fusão automática baseada em similaridade textual;
- inferência de aliases;
- escolha automática entre fontes oficiais conflitantes.

Quando não houver segurança suficiente, o sistema deve preservar
a incerteza e solicitar revisão.

## 9. Evolução

A política poderá ser ampliada após avaliação de casos reais, mantendo
a compatibilidade com os identificadores internos já persistidos.
