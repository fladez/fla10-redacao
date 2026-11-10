# Configuração local do MVP

Este guia prepara o ambiente de desenvolvimento. Nenhuma credencial deve ser enviada pelo chat ou gravada no Git.

## 1. Requisitos

- macOS ou Linux;
- Python 3.11 ou superior;
- Git;
- acesso ao repositório privado `rcorreas/Redacao-Fla10`.

## 2. Credencial GitHub somente leitura

Criar um fine-grained personal access token no GitHub:
1. Abrir Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Gerar um token com nome `Fla10-Agents-readonly`.
3. Em Resource owner, selecionar `rcorreas`.
4. Em Repository access, selecionar **Only select repositories** e marcar apenas `Redacao-Fla10`.
5. Em Repository permissions, conceder **Contents: Read-only**. Não conceder permissões de escrita. Metadata é a permissão básica de leitura do repositório.
6. Definir validade limitada, por exemplo 90 dias, e gerar o token.

Não conceder Contents: Read and write. O MVP não precisa alterar o repositório editorial.

O GitHub recomenda tokens fine-grained, acesso restrito aos repositórios necessários e permissões mínimas. Consulte a [documentação oficial](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

**Nunca cole o token nesta conversa, em arquivos versionados ou em capturas de tela.**

## 3. Preparar o projeto

Na pasta local em que deseja guardar o projeto:

```bash
git clone https://github.com/rcorreas/Fla10-Agents.git
cd Fla10-Agents
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Se a instalação editável não tiver efeito — alguns interpretadores ignoram
arquivos `.pth` dentro de diretórios ocultos, como `.venv` —, use uma das
duas alternativas:

```bash
# instalação normal; repita após cada alteração no código
pip install ".[dev]"

# execução direta do código-fonte, sem reinstalar
PYTHONPATH=src python -m fla10_agents calendar list
```

O comando `fla10` só passa a refletir o código novo depois da reinstalação;
`python -m fla10_agents` executa sempre o conteúdo atual de `src/`.

## 4. Configurar ambiente

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Edite o arquivo `.env` e informe o token GitHub em `GITHUB_TOKEN`. Mantenha o restante como está, salvo necessidade explícita. O arquivo `.env` é ignorado pelo Git.

Para executar o teste comparativo dos modelos e a produção editorial, informe também a chave do OpenRouter em `OPENROUTER_API_KEY`. A chave deve ser criada em https://openrouter.ai/settings/keys e guardada somente no arquivo local `.env`. Não a cole no chat, não a inclua em capturas de tela e não a versione no Git.

A produção usa `FLA10_WRITING_MODEL` (padrão provisório `openai/gpt-5.5`) e a revisão usa `FLA10_REVIEW_MODEL`; quando a segunda não está definida, a revisão usa o mesmo modelo da redação. Os IDs precisam existir no catálogo do OpenRouter e não há fallback silencioso para outro modelo.

O módulo de avaliação usa o endpoint OpenRouter e os IDs documentados em `docs/11-protocolo-avaliacao-modelos.md`. Não é necessária uma chave direta da OpenAI para essa comparação. `OPENAI_API_KEY` permanece reservado a futuras integrações diretas.

## 5. Executar testes locais

```bash
pytest
ruff check .
mypy src
```

Os testes automatizados não fazem chamadas pagas ao OpenRouter e não exigem uma chave válida.

O banco local do calendário fica em `data/calendar.db` na raiz do projeto. Para apontar para outro arquivo, use `--database` ou defina a variável `FLA10_DATABASE` no ambiente. O banco é criado automaticamente na primeira execução, com versão de schema registrada em `PRAGMA user_version`; a abertura migra estruturas antigas e recusa bancos de versão mais nova.

O estado editorial (sinais, propostas, dossiês e matérias publicadas) fica em `data/editorial.db`. Para outro arquivo, use `--database` nos comandos editoriais ou defina `FLA10_EDITORIAL_DATABASE`.

A Fase 1 lê o vault local em modo somente leitura. Por padrão, usa `~/Documents/Redacao-Fla10`; para outro caminho, defina `EDITORIAL_VAULT_PATH` ou use `--vault` nos comandos `vault` e `pautas parse`. O vault nunca é alterado.

## 6. Verificar acesso real ao repositório editorial

Com o ambiente virtual ativo e o token configurado no `.env`, executar:

```bash
fla10 check-editorial
```

O resultado deve informar repositório, branch, commit SHA e nomes dos quatro documentos lidos. O token nunca é exibido.

Se o comando retornar erro 401 ou 403, conferir a validade do token, o repositório selecionado e a permissão Contents: Read-only. Não ampliar permissões para escrita como tentativa de resolver erro de leitura.

## 7. Executar o primeiro teste comparativo

Depois de configurar a chave OpenRouter, executar:

```bash
fla10 run-report-test
```

O programa envia o mesmo prompt e o mesmo dossiê aos três modelos, sem habilitar pesquisa externa. As respostas recebem rótulos cegos e são salvas localmente em `artifacts/model-evaluation/`, junto com metadados de uso e um arquivo separado que identifica cada modelo.

O diretório `artifacts/` é ignorado pelo Git. Não enviar a chave de cegamento antes de concluir a avaliação cega. A primeira execução pode gerar cobrança no OpenRouter; consulte o preço dos modelos no dia do teste e defina um limite de gastos na conta.

A chamada não permite fallback silencioso para outro modelo. Se um endpoint falhar, o comando informa o modelo e interrompe a execução; não substitui o modelo por outro.

## 8. Produção, revisão e publicação assistida

O fluxo editorial usa o mesmo `OPENROUTER_API_KEY`:

```bash
fla10 redacao gerar ID_DA_PROPOSTA
fla10 redacao revisar ID_DO_TEXTO
fla10 redacao list
fla10 redacao mostrar ID_DO_TEXTO
fla10 redacao aprovar ID_DO_TEXTO
```

Para revisar sem chamada de modelo:

```bash
fla10 redacao revisar ID_DO_TEXTO --deterministico
```

A geração exige pauta `approved` e dossiê com recomendação `pronto para redação`. O texto gerado fica em `awaiting_human` até a decisão do editor. A aprovação é recusada se a revisão mais recente for `bloqueado`.

Depois da aprovação, prepare e exporte o pacote:

```bash
fla10 publicacao preparar ID_DO_TEXTO
fla10 publicacao exportar ID_DO_PACOTE --output exports/
fla10 publicacao list
```

A exportação grava `article.html`, `article.md`, `package.json` e `metadata.json` em `exports/PACKAGE_ID/`. Nada é enviado ao site.

Somente depois de publicar manualmente, registre a confirmação:

```bash
fla10 publicacao registrar ID_DO_PACOTE \
  --url "https://fla10.news/materia" \
  --published-at "2026-11-10T18:00:00-03:00" \
  --confirmar "Confirmado no painel do site"
```

O registro exige URL válida, data com fuso e confirmação não vazia. Ele também inclui o título em `published_articles`, alimentando a checagem de redundância. Sem esses dados, o pacote permanece `exported`.

## 9. Segurança

- Não versionar `.env`.
- Não registrar credenciais em logs.
- Não compartilhar a chave OpenRouter no chat.
- Revogar qualquer chave que tenha sido exposta.
- Não usar a credencial do conector de administração para o processo de execução.
- Não habilitar escrita no Redacao-Fla10 para os agentes do MVP.
