# Fluxo MVP — Calendário, Pautas e Apuração

## 1. Resultado esperado

Dado um calendário esportivo e o monitoramento de fontes, o sistema identifica eventos e fatos novos, compara-os com a memória editorial, recomenda pautas com recorte próprio e prepara dossiês verificáveis. O editor humano decide o que será produzido.

O MVP não redige matérias completas, não altera o painel editorial, não publica e não envia conteúdo a terceiros.

## 2. Agente Calendário e Agenda

### Entradas
- calendários e tabelas oficiais das competições;
- agenda oficial do Flamengo;
- fontes oficiais das federações e ligas da modalidade;
- agenda editorial já registrada no Redacao-Fla10.

### Dados normalizados por evento
- identificador interno estável;
- modalidade e categoria (equipe principal, base, feminino etc.);
- competição, fase/rodada e temporada;
- participantes e mando;
- data/hora local, fuso e precisão da informação;
- estádio/local;
- situação do evento (confirmado, provisório, adiado, cancelado ou divergente);
- URL e tipo de cada fonte;
- momento da última consulta.

### Regras
- priorizar fonte oficial para calendário, regulamento e dados formais;
- não inferir horário, local ou transmissão ausentes;
- detectar mudanças e preservar o valor anterior no histórico;
- divergência entre fontes oficiais gera alerta, não escolha silenciosa;
- a agenda do vault é contexto editorial, não substituto da reconfirmação externa de dados dinâmicos.

## 3. Conversão de evento em proposta de cobertura

O fluxo de produção do Redacao-Fla10 define a cobertura por categoria:

### Futebol masculino profissional — equipe principal
- véspera: Onde Assistir;
- dia do jogo: Pré-jogo;
- após a partida: Pós-jogo;
- depois de apuração adicional: Análise jornalística;
- após o jogo: Depois do Apito;
- após observação e dados suficientes: Raio-X Tático.

### Demais categorias e modalidades
Inclui expressamente futebol masculino de base, como Sub-20 e Sub-17.
- véspera: Onde Assistir, quando houver pauta de serviço prevista;
- após o evento: Pós-jogo, quando houver informações confiáveis e suficientes;
- não gerar automaticamente a sequência especial da equipe principal.

A criação dessas sugestões não aprova as pautas. O coordenador deve apresentá-las ao editor para decisão.

## 4. Agente Monitoramento e Pautas

### Entradas
- eventos do Calendário e Agenda;
- notícias, comunicados, entrevistas e documentos novos;
- Painel de Pautas e Projetos e Pautas Reservadas;
- matérias publicadas e fichas históricas relacionadas.

### Processo
1. identificar o fato novo e a fonte original;
2. classificar a informação como oficial, apuração jornalística, especializada ou pista não confirmada;
3. comparar com pautas publicadas, reservadas e canceladas;
4. definir a pergunta editorial que o leitor precisa ver respondida;
5. explicar o que a pauta acrescenta e o que não deve repetir;
6. listar fatos a confirmar, fontes e riscos;
7. recomendar prioridade sem aprovar a produção.

### Entrega — proposta de pauta
- título provisório;
- fato gerador e data;
- pergunta editorial;
- recorte/ângulo exclusivo;
- modalidade, competição e formato;
- por que publicar agora;
- fatos confirmados e informações atribuídas;
- fontes primárias e secundárias iniciais;
- matérias e reservas relacionadas;
- risco de redundância;
- perguntas para apuração;
- recomendação de prioridade;
- decisão humana pendente.

## 5. Agente Apuração e Verificação

Após aprovação humana da pauta:
1. transformar o briefing em perguntas verificáveis;
2. buscar primeiro a origem primária;
3. localizar a origem de informações atribuídas;
4. confirmar de forma independente afirmações decisivas ou controversas;
5. verificar data, autoria, contexto e atualização de cada fonte;
6. registrar circularidade entre matérias que reproduzem a mesma origem;
7. identificar contradições, lacunas e afirmações que devem ser excluídas;
8. produzir um dossiê para uso editorial.

### Classificação das afirmações
- confirmada;
- atribuída;
- contexto;
- análise;
- hipótese/cenário;
- não confirmada.

A classificação não é uma nota numérica de confiança. A evidência e a limitação devem estar descritas para permitir julgamento humano.

### Entrega — dossiê de apuração
- pauta/ID e pergunta editorial;
- data da apuração;
- tabela de afirmações, classificação, evidências e limitações;
- tabela de fontes, tipo, autoria, data, URL e o que sustentam;
- contradições;
- lacunas e perguntas pendentes;
- informações utilizáveis;
- informações que exigem atribuição;
- hipóteses que podem ser tratadas como análise;
- afirmações excluídas;
- recomendação: apuração suficiente, insuficiente ou bloqueada.

## 6. Pontos de aprovação humana

| Momento | Decisão |
|---|---|
| Proposta de pauta | Aprovar, ajustar, reservar, adiar ou cancelar |
| Dossiê de apuração | Autorizar produção, pedir nova apuração ou interromper |
| Conflito factual relevante | Decidir recorte ou suspender a pauta |
| Alteração no painel do vault | Fora do MVP; exige autorização e fluxo específico futuro |
| Publicação | Fora do MVP |

## 7. Estados e histórico

Manter separadamente:
- estado editorial conforme Gestão de Pautas do vault;
- estado técnico da tarefa e da execução do agente.

Toda execução registra entrada, fontes consultadas, commit do vault, saída, erros e horário. Uma proposta não aprovada continua sendo proposta; uma apuração concluída não significa pauta pronta para publicação.

## 8. Exemplo de execução

**Evento:** partida oficial do Flamengo identificada em calendário.

1. Calendário registra o evento e as fontes.
2. Coordenador consulta a agenda e a memória editorial.
3. Monitoramento verifica se há notícia nova relacionada e se existe cobertura já publicada/reservada.
4. Sistema apresenta a sugestão de Onde Assistir e, conforme a modalidade, as coberturas previstas.
5. Editor aprova ou altera a programação.
6. Apuração confirma transmissão, horário, local, fase, prováveis escalações e arbitragem apenas quando divulgados e verificáveis.
7. O dossiê separa o que está confirmado do que permanece pendente.
8. O fluxo aguarda decisão humana; não escreve no vault nem publica.

## 9. Critérios de aceite do MVP

- eventos com origem e horário de consulta rastreáveis;
- mudanças de calendário detectadas sem apagar histórico;
- propostas de pauta que respeitam a distinção entre equipe principal e demais modalidades;
- alertas de redundância acompanhados de links e razões;
- dossiês em que cada afirmação relevante aponta para evidência;
- incertezas e contradições explícitas;
- nenhuma alteração no Redacao-Fla10 ou publicação externa;
- decisões humanas registradas separadamente das saídas dos agentes.
