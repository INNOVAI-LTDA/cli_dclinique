---
description: "Executa Macro-run A: estabilização técnica e consolidação do mock_data"
name: "Macro-run A"
agent: "map-implementacao"
argument-hint: "Opcional: detalhe adicional do foco desta rodada"
---
Você está na Macro-run A (Base técnica) deste projeto Streamlit.

Objetivo:
1) Corrigir qualquer erro que impeça streamlit run app.py.
2) Consolidar src/mock_data.py garantindo que load_mock_data() retorne os DataFrames esperados.
3) Garantir consistência de IDs entre tabelas.

Restrições obrigatórias:
- Não alterar o escopo funcional definido para esta rodada.
- Não implementar parser real, Supabase, login, deploy ou integrações externas.
- Preservar nomes de campos e contrato de dados de src/mock_data.py.
- Antes de editar, listar rapidamente os arquivos que serão alterados.
- Após editar, validar execução local e reportar erros remanescentes.
- Entregar resumo final com arquivos alterados, impacto e riscos.
