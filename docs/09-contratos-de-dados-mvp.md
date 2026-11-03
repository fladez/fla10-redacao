# Contratos de dados — MVP

Este documento define os objetos mínimos de intercâmbio. É um contrato lógico inicial; os modelos Python e as tabelas SQLite serão derivados dele e validados por testes.

## 1. Evento esportivo

```json
{
  "event_id": "stable-internal-id",
  "sport": "football",
  "category": "mens_team_first_team",
  "competition": "competition name",
  "season": "season",
  "stage": "round or phase",
  "home_team": "team",
  "away_team": "team",
  "starts_at_local": "YYYY-MM-DDTHH:MM:SS",
  "timezone": "America/Sao_Paulo",
  "venue": "venue or null",
  "event_status": "confirmed",
  "sources": [
    {
      "url": "https://source.example",
      "source_type": "official",
      "checked_at": "ISO-8601 timestamp",
      "supports": ["date", "time", "venue"]
    }
  ],
  "last_verified_at": "ISO-8601 timestamp"
}
```

Campos desconhecidos devem ser nulos ou ausentes, nunca preenchidos por inferência. `event_status` aceita inicialmente: `confirmed`, `provisional`, `postponed`, `cancelled`, `conflicting`.

## 2. Proposta de pauta

```json
{
  "proposal_id": "stable-internal-id",
  "title": "provisional headline",
  "event_id": "event-id-or-null",
  "format": "onde_assistir",
  "editorial_question": "question the story answers",
  "angle": "distinct editorial angle",
  "why_now": "timeliness",
  "confirmed_facts": [],
  "attributed_information": [],
  "questions_to_verify": [],
  "initial_sources": [],
  "related_published": [],
  "related_reserved": [],
  "redundancy_risk": "low",
  "priority_recommendation": "normal",
  "editorial_decision": "awaiting_human"
}
```

`redundancy_risk` é sinalização, não decisão automática. `editorial_decision` será controlada pelo editor; o agente não pode aprovar a própria pauta.

## 3. Evidência e afirmação

```json
{
  "claim_id": "stable-internal-id",
  "claim_text": "one factual assertion",
  "classification": "confirmed",
  "evidence": [
    {
      "source_id": "source-id",
      "url": "https://source.example",
      "source_type": "primary",
      "author_or_institution": "publisher",
      "published_at": "ISO-8601 timestamp or null",
      "accessed_at": "ISO-8601 timestamp",
      "supporting_excerpt_or_data": "short excerpt or exact value",
      "limitations": "scope and caveats"
    }
  ],
  "independent_corroboration": "present",
  "open_questions": []
}
```

Classificações: `confirmed`, `attributed`, `context`, `analysis`, `hypothesis`, `unconfirmed`. Não converter classificação em pontuação numérica sem método validado.

## 4. Dossiê de apuração

Deve conter identificação da pauta, pergunta editorial, data, afirmações, evidências, fontes, contradições, lacunas, fatos utilizáveis, atribuições necessárias, hipóteses admissíveis, afirmações excluídas e recomendação de suficiência.

## 5. Referência ao conhecimento editorial

Toda execução que consultar o vault deve registrar:
- repositório;
- branch;
- commit SHA;
- caminhos lidos;
- horário de leitura;
- resultado da leitura (sucesso/falha).

Não copiar o conteúdo das regras para os registros de cada tarefa; guardar referências ao arquivo e commit.

## 6. Estados separados

```json
{
  "editorial_status": "em_apuracao",
  "operational_status": "succeeded"
}
```

Os valores editoriais seguem o documento Gestão de Pautas do Redacao-Fla10. Os estados operacionais são internos ao sistema. A atualização de um eixo não altera automaticamente o outro.

## 7. Convenções técnicas

- Identificadores internos estáveis e não dependentes do título.
- Datas de auditoria em ISO 8601 UTC; horário do evento sempre acompanhado de fuso.
- Preservar URL original e data de acesso.
- Não sobrescrever versões antigas de eventos, evidências ou dossiês sem histórico.
- Validar entradas e saídas por esquema antes de persistir ou encaminhar a outro agente.
