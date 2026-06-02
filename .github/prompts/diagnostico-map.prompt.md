---
description: "Executa diagnóstico inicial e plano priorizado antes de qualquer macro-run"
name: "Diagnóstico MAP"
agent: "map-diagnostico"
argument-hint: "Opcional: foco do diagnóstico (ex.: streamlit run, schema, navegação)"
---
Você está na etapa de diagnóstico inicial do projeto MAP em Streamlit.

Objetivo:
1) Detectar riscos técnicos antes de editar.
2) Priorizar problemas por impacto (P0, P1, P2).
3) Definir plano curto para o próximo macro-run.

Restrições obrigatórias:
- Não editar arquivos.
- Não expandir escopo funcional.
- Não incluir parser real, Supabase, login, deploy ou integrações externas.

Saída obrigatória:
- Resumo executivo (até 5 linhas).
- Problemas por prioridade (P0, P1, P2).
- Plano de execução em passos objetivos.
- Critérios de pronto para iniciar implementação.
