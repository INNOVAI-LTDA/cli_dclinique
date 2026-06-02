# Plano de Execução — Codex Web + Codex VS Code

## Estratégia

Usar duas etapas complementares:

```text
Codex Web
  → gera o scaffold completo e a primeira versão navegável

Codex no VS Code
  → roda localmente, corrige erros, ajusta layout e refina detalhes
```

## Por que usar Codex Web primeiro

O repositório ainda está sem estrutura. O Codex Web é ideal para receber uma tarefa fechada e gerar múltiplos arquivos de uma vez: estrutura do projeto, páginas, componentes, dados mockados, README e requirements.

## Por que usar Codex no VS Code depois

Streamlit precisa ser testado visualmente. O VS Code permite rodar localmente, ver erros, ajustar a navegação, corrigir imports e mexer em componentes pontuais.

## Objetivo da Etapa 1 — Codex Web

Criar uma primeira versão executável do app:

```text
streamlit run app.py
```

Com:

- sidebar navegável;
- dados fictícios;
- telas principais;
- ficha de paciente;
- gráficos;
- tabelas;
- alertas;
- qualidade de dados;
- arquitetura modular.

## Objetivo da Etapa 2 — Codex VS Code

Refinar:

- erros de import;
- erros de runtime;
- navegação com `st.session_state`;
- visual das páginas;
- layout dos cards;
- seleção de paciente;
- organização do código;
- validação local.

## O que não fazer nesta rodada

Não pedir:

- parser real de PDF;
- parser real de Excel;
- Supabase;
- login;
- deploy;
- WhatsApp;
- Google Drive;
- integração real com dados clínicos.

Essa rodada é para **casca navegável com dados mockados fiéis ao banco futuro**.

## Fluxo recomendado

```text
1. Criar ou abrir repositório GitHub vazio.
2. Adicionar este bundle ao repositório.
3. Rodar Codex Web usando o prompt principal.
4. Revisar arquivos criados.
5. Clonar/abrir no VS Code.
6. Criar ambiente Python.
7. Instalar dependências.
8. Rodar Streamlit.
9. Usar Codex VS Code para correções.
10. Fazer commit da primeira versão.
```
