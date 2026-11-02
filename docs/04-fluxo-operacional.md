# Fluxo operacional

## 1. Ciclo padrão
1. Entrada: solicitação humana, evento de calendário ou sinal de monitoramento.
2. Triagem: coordenador classifica modalidade, urgência e dependências.
3. Proposta: Monitoramento e Pautas apresenta oportunidade e recorte.
4. Aprovação: editor decide se a pauta será executada.
5. Apuração: Apuração e Verificação prepara dossiê.
6. Redação: Produção escreve com base no dossiê e nas regras aplicáveis.
7. Revisão: Controle de Qualidade verifica independentemente.
8. Avaliação humana: editor aprova, pede ajustes ou cancela.
9. Publicação assistida: preparar; executar somente com autorização explícita.
10. Registro: após confirmação, registrar URL, data, versão e histórico.
11. Auditoria: avaliar amostras, erros e melhorias.

## 2. Estados
- **Pendente:** ainda não iniciada.
- **Em andamento:** execução iniciada.
- **Bloqueada:** depende de informação, permissão ou decisão.
- **Aguardando aprovação:** entrega pronta para decisão humana.
- **Concluída:** critério de conclusão atendido, sem implicar publicação.
- **Publicada:** publicação confirmada por evidência ou confirmação explícita.
- **Cancelada:** encerrada por decisão registrada.
- **Falhou:** execução não atingiu o resultado esperado.

Concluída não é sinônimo de publicada.

## 3. Contrato mínimo de tarefa
ID único; objetivo e tipo; agente responsável; contexto e referências; entradas e dependências; restrições e permissões; prazo/prioridade; critério de conclusão; estado e tentativas; timestamps; resultado e artefatos; aprovações e histórico.

## 4. Contrato mínimo de apuração
Cada afirmação relevante aponta para evidência. Registrar fonte, URL/identificador, autoria, data de publicação e acesso, trecho/dado de suporte e classificação. Classificações: confirmado por fonte primária; corroborado por fontes independentes; relato atribuído; não confirmado; contraditório; hipótese/análise.

## 5. Regras editoriais
Consultar Redacao-Fla10 para identificar o formato aplicável. Respeitar estrutura, tom, marcadores de parágrafo e subtítulo e requisitos específicos vigentes. Em caso de conflito ou ausência de instrução, interromper e pedir decisão.

## 6. Bloqueios
Interromper diante de divergência central entre fontes confiáveis, informação essencial não confirmada, decisão editorial necessária, instruções conflitantes, permissão insuficiente ou falha de integração sem alternativa segura.

## 7. Registro de publicação
Guardar URL final, título, data/hora, responsável pela confirmação e versão entregue. Ação externa só é considerada concluída após retorno positivo e verificação do resultado.
