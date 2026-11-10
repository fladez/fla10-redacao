# Protocolo de avaliação comparativa de modelos — reportagem aprofundada

**Projeto:** Fla10-Agents  
**Caso:** A força da Nação — poder econômico e influência da torcida do Flamengo  
**Versão:** 1.0  
**Status:** suspenso. O projeto opera inicialmente com o DeepSeek V4.1 Flash Free pelo OpenCode, com custo zero. Este protocolo documenta uma avaliação comparativa paga opcional e só pode ser executado com `FLA10_ENABLE_PAID_EVALUATION=1`.

## 1. Objetivo

Comparar a capacidade de três modelos de transformar um mesmo dossiê documental em uma reportagem aprofundada, obedecendo às diretrizes editoriais da Fla10.

O teste mede qualidade jornalística, não apenas fluência textual. Nenhum resultado autoriza publicação automática ou substitui a decisão do editor.

## 2. Modelos candidatos

Os identificadores abaixo são os IDs públicos exibidos no catálogo OpenRouter consultado em 08/11/2026:

| Rótulo cego | Modelo | ID OpenRouter |
|---|---|---|
| Modelo A | OpenAI GPT-5.5 | `openai/gpt-5.5` |
| Modelo B | OpenAI GPT-4o-mini | `openai/gpt-4o-mini` |
| Modelo C | Qwen2.5-72B Instruct | `qwen/qwen-2.5-72b-instruct` |

Referências de catálogo:
- GPT-5.5: https://openrouter.ai/openai/gpt-5.5
- GPT-4o-mini: https://openrouter.ai/openai/gpt-4o-mini
- Qwen2.5-72B: https://openrouter.ai/qwen/qwen-2.5-72b-instruct

Preços e disponibilidade mudam. Consultar o catálogo no dia da execução e registrar o preço efetivamente aplicado. O Qwen2.5-72B tem janela de contexto anunciada de 32.768 tokens no catálogo atual, não 128 mil; por isso o pacote de entrada deve ser medido antes do envio. Não exceder a janela do menor modelo.

## 3. Desenho experimental

### Rodada 1 — redação com dossiê fechado

- Os três modelos recebem exatamente o mesmo prompt e o mesmo pacote de fontes.
- Navegação, busca na web e ferramentas externas ficam desativadas.
- Os modelos não recebem a reportagem publicada como exemplo nem seu texto integral. Isso evita que apenas reescrevam a versão já editada.
- Cada modelo gera uma única versão inicial, sem diálogo de refinamento.
- A saída é armazenada integralmente, junto com ID exato do modelo, provedor efetivo quando informado, data/hora, parâmetros, tokens de entrada/saída, latência, custo e eventuais erros.
- Usar a mesma configuração de geração sempre que suportada: temperatura 0,2, top_p 1 e limite de saída comum de 7.000 tokens. Se algum endpoint não aceitar um parâmetro, registrar a diferença em vez de simular equivalência.
- Não habilitar fallback silencioso para outro modelo. Se o endpoint falhar, registrar falha e repetir apenas após identificar a causa.

### Cegamento

Depois das três respostas, atribuir códigos aleatórios (Texto X, Y e Z), remover metadados que revelem o modelo e avaliar sem conhecer a autoria. Guardar a tabela de correspondência separadamente até o encerramento das notas.

### Rodada 2 — apuração assistida (posterior)

Somente depois da Rodada 1. Comparará a capacidade de encontrar e verificar fontes, com o mesmo acesso, janela temporal, ferramentas e critérios. Não misturar os resultados das duas rodadas.

## 4. Prompt comum de produção

O prompt integral está em `docs/12-prompt-comum-teste-reportagem.md`. Não adaptar individualmente para nenhum modelo.

## 5. Critérios e pesos

Cada dimensão recebe nota de 0 a 10, acompanhada de justificativa e exemplos verificáveis.

| Critério | Peso |
|---|---:|
| Precisão factual e respeito às evidências | 25% |
| Profundidade, contexto e capacidade explicativa | 20% |
| Qualidade narrativa e organização | 20% |
| Raciocínio, coerência e tratamento das limitações | 15% |
| Cumprimento das diretrizes editoriais Fla10 | 10% |
| SEO e estrutura de publicação | 10% |

**Cálculo:** soma de (nota da dimensão × peso). A nota final não elimina a obrigação de registrar erros graves individualmente.

### Registro obrigatório de problemas

- Afirmações factuais sem suporte no dossiê.
- Números alterados, arredondados indevidamente ou apresentados sem contexto.
- Confusão entre estimativa, declaração institucional, projeção, contrato e receita realizada.
- Causalidade afirmada sem evidência.
- Fontes, entrevistas, documentos ou respostas inventados.
- Omissão de ressalvas centrais.
- Confusão entre torcedores, seguidores, consumidores, sócios e frequentadores.
- Repetição, clichê, superficialidade ou texto genérico.
- Falhas de estrutura, HTML, resumo para IA e pacote SEO.

Erro factual grave pode desclassificar um texto da condição de vencedor, mesmo que a pontuação média seja alta.

## 6. Regras de integridade

1. Não completar lacunas com inferências apresentadas como fatos.
2. Não inventar entrevistas, respostas do Flamengo, patrocinadores ou pesquisadores.
3. Não transformar números de campanhas em consumidores únicos, vendas incrementais ou lucro.
4. Não tratar estimativa institucional de 45 milhões como contagem independente.
5. Não usar 68 milhões de inscrições como indivíduos únicos.
6. Não calcular conversão dividindo sócios por estimativa de torcedores.
7. Não atribuir crescimento de vendas ou receitas ao patrocínio sem estudo de causalidade.
8. Não somar contratos, receitas contábeis e projeções como se fossem grandezas equivalentes.
9. Identificar a origem e as limitações de cada dado.
10. Se o dossiê não sustentar uma afirmação, omitir ou qualificar explicitamente.

## 7. Critério de decisão

A recomendação de modelo principal será baseada em:
- nota editorial cega;
- quantidade e gravidade de erros;
- esforço de correção exigido do editor;
- custo total da geração;
- estabilidade e cumprimento do formato.

Não escolher apenas pelo menor custo ou pela maior nota de estilo. Se os resultados forem próximos, executar novas pautas antes de concluir.

## 8. Estado

- [x] Caso editorial selecionado.
- [x] Dossiê e ressalvas recuperados do repositório editorial.
- [x] Modelos candidatos e IDs definidos para a primeira rodada.
- [x] Prompt comum preparado.
- [ ] Confirmar a configuração segura da chave OpenRouter no computador do editor.
- [ ] Validar tamanho do pacote de entrada contra o limite do menor modelo.
- [ ] Executar as três gerações.
- [ ] Cegar os textos e avaliar.
- [ ] Produzir relatório comparativo.

## 9. Proveniência do dossiê

O caso foi recuperado do histórico editorial do repositório `rcorreas/Redacao-Fla10`. Principais registros:
- Ampliação cultural, Nação Sem Fronteiras e patrocínios: https://github.com/rcorreas/Redacao-Fla10/commit/78b2451a14c595a911b25df8b67350a58985d689
- Casos Shopee, Lubrax, CRMBonus e rede de embaixadas: https://github.com/rcorreas/Redacao-Fla10/commit/1436e759cab946993a588d0ebf031efd9a965b28
- Estudos acadêmicos e segmentação de torcedores: https://github.com/rcorreas/Redacao-Fla10/commit/45c646fb044234723a9f5413610e596c753bd8c2
- Registro de publicação e síntese editorial: https://github.com/rcorreas/Redacao-Fla10/commit/4571f3a4bf7fec83ea9628ef4b6878c88e533f50

A pauta registra que entrevistas e pedidos institucionais foram preparados, mas não enviados. Não existem respostas dessas fontes no material recuperado.
