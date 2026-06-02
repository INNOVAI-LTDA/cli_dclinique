# Tasks Sequenciais para Execução Controlada

Se quiser reduzir risco, em vez de mandar o prompt gigante de uma vez, use estas tarefas no Codex Web/VS Code.

## Task 1 — Estrutura

```text
Crie a estrutura inicial do projeto Streamlit conforme a spec. Não implemente todas as telas ainda. Crie app.py, requirements.txt, README.md, src/, src/pages/, src/components/, src/charts/ e src/mock_data.py.
```

## Task 2 — Dados mockados

```text
Implemente `src/mock_data.py` com a função `load_mock_data()` retornando todos os DataFrames esperados e pelo menos 8 pacientes fictícios com cenários variados.
```

## Task 3 — Navegação

```text
Implemente sidebar e navegação com `st.session_state`. Crie páginas vazias funcionais para todas as telas.
```

## Task 4 — Visão Geral

```text
Implemente a tela Visão Geral com KPIs, gráfico e lista de pacientes em atenção usando os dados mockados.
```

## Task 5 — Pacientes e Ficha

```text
Implemente a tela Pacientes e a Ficha do Paciente. A seleção de paciente deve abrir a ficha correta.
```

## Task 6 — Mapa de Decisão

```text
Implemente o Mapa de Decisão 2x2 usando engajamento e satisfação dos dados mockados.
```

## Task 7 — Alertas

```text
Implemente a tela Alertas com filtros por categoria e abertura da ficha do paciente.
```

## Task 8 — Atualização e Qualidade

```text
Implemente as telas Atualização de Dados e Qualidade dos Dados como telas demonstrativas.
```

## Task 9 — Polimento

```text
Revise layout, componentes, README, erros e inconsistências. Garanta que `streamlit run app.py` funcione.
```
