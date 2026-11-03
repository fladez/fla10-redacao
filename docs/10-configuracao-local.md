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

## 4. Configurar ambiente

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Edite o arquivo `.env` e informe o token GitHub em `GITHUB_TOKEN`. Mantenha o restante como está, salvo necessidade explícita. O arquivo `.env` é ignorado pelo Git.

Não é necessário configurar uma chave OpenAI para testar o adaptador de leitura do GitHub. A chave será necessária somente quando iniciarmos execuções reais com o Agents SDK.

## 5. Executar testes

```bash
pytest
ruff check .
```

Os testes do adaptador usam respostas simuladas; não fazem chamadas reais ao GitHub e não exigem token válido.

## 6. Verificar acesso real

Com o ambiente virtual ativo e o token configurado no `.env`, executar:

```bash
fla10 check-editorial
```

O resultado deve informar repositório, branch, commit SHA e nomes dos quatro documentos lidos. O token nunca é exibido.

Se o comando retornar erro 401 ou 403, conferir a validade do token, o repositório selecionado e a permissão Contents: Read-only. Não ampliar permissões para escrita como tentativa de resolver erro de leitura.

## 7. Segurança

- Não versionar `.env`.
- Não registrar o token em logs.
- Não usar a credencial do conector de administração para o processo de execução.
- Revogar o token se houver exposição.
- Não habilitar escrita no Redacao-Fla10 para os agentes do MVP.
