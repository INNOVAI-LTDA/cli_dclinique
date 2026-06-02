# Bundle — Execução com Codex Web + Codex VS Code

Este pacote foi preparado para um repositório GitHub ainda sem estrutura.

Objetivo:

> Usar **Codex Web** para gerar o primeiro scaffold completo da casca navegável em Streamlit e depois usar **Codex no VS Code** para rodar, depurar, ajustar e refinar.

## Conteúdo

| Arquivo | Uso |
|---|---|
| `01_PLANO_EXECUCAO_CODEX.md` | Visão geral da estratégia em duas etapas |
| `02_CODEX_WEB_PROMPT.md` | Prompt principal para usar no Codex Web |
| `03_CODEX_WEB_CRITERIOS_ACEITE.md` | Checklist para aceitar a entrega do Codex Web |
| `04_CODEX_VSCODE_PROMPTS.md` | Prompts para ajustes no VS Code |
| `05_CHECKLIST_VALIDACAO_LOCAL.md` | Passo a passo para rodar localmente |
| `06_ESTRUTURA_REPO_ESPERADA.md` | Estrutura de pastas e arquivos esperados |
| `07_TASKS_SEQUENCIAIS.md` | Sequência de tarefas para execução controlada |
| `08_GITHUB_PR_TEMPLATE.md` | Template de Pull Request |
| `09_TROUBLESHOOTING_STREAMLIT.md` | Erros comuns e como pedir correção ao Codex |
| `10_PROMPT_CURTO_CONTINUACAO.md` | Prompt curto para continuar iterações |
| `00_spec_base/` | Spec anterior da casca navegável, quando disponível |

## Modo de uso

1. Suba este conteúdo no repositório GitHub.
2. Use `02_CODEX_WEB_PROMPT.md` no Codex Web.
3. Aguarde o Codex gerar a primeira versão.
4. Abra o projeto no VS Code.
5. Use `04_CODEX_VSCODE_PROMPTS.md` para correções e ajustes.
6. Rode o checklist de validação local.

## Escopo desta rodada

Esta rodada **não** é para implementar parser real, Supabase, login, deploy ou WhatsApp.

É para gerar:

- app Streamlit navegável;
- telas principais;
- dados fictícios aderentes ao modelo de banco;
- navegação para ficha do paciente;
- gráficos e tabelas coerentes;
- estrutura modular para conectar dados reais depois.
