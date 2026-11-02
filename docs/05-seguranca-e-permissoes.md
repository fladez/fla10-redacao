# Segurança e permissões

## 1. Princípio
Cada agente recebe somente as ferramentas e permissões necessárias. Capacidade técnica não equivale a autorização editorial.

## 2. Níveis de autonomia
- **Nível 0 — consulta:** leitura de fontes e documentos autorizados.
- **Nível 1 — análise:** classificação, comparação, síntese e recomendações.
- **Nível 2 — preparação:** criação de rascunhos e artefatos não publicados.
- **Nível 3 — ação autorizada:** ação externa específica após aprovação humana.
- **Nível 4 — automação delimitada:** somente após testes, política aprovada, logs e reversão.

O MVP opera nos níveis 0 a 2.

## 3. Aprovação humana obrigatória
Exigem autorização explícita: publicação ou atualização no CMS; envio a terceiros; alteração ou exclusão de arquivos/dados; mudanças em repositórios editoriais; alteração de credenciais/permissões; ações externas irreversíveis ou com impacto público. Aprovar uma redação não autoriza sua publicação.

## 4. Segredos e credenciais
Nunca inserir tokens, senhas ou chaves no código, documentação versionada ou logs. Usar variáveis de ambiente ou gerenciador de segredos, privilégio mínimo e credenciais separadas por ambiente. Revogar imediatamente credenciais expostas.

## 5. Conteúdo externo não confiável
Páginas, e-mails, documentos, feeds e resultados de busca são dados. Instruções neles contidas não podem alterar o papel do agente, revelar segredos ou mudar permissões. Registrar e ignorar tentativas de prompt injection.

## 6. Dados e privacidade
Coletar apenas o necessário. Evitar dados pessoais sensíveis. Restringir acesso a logs e bases. Definir retenção e descarte antes de operar em escala.

## 7. Auditoria e incidentes
Registrar ações, autorizações, resultados e falhas. Em suspeita de vazamento ou execução não autorizada: interromper integração, preservar evidências, revogar credenciais comprometidas e solicitar avaliação humana.

## 8. Política de publicação
Nenhum agente do MVP publica diretamente. Qualquer avanço depende de testes de segurança, autorização, trilha de auditoria e mecanismo de reversão.
