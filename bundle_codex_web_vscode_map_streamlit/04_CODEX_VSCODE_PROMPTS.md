# Prompts para Codex no VS Code

Use estes prompts depois que o Codex Web gerar a primeira estrutura.

## 1. Corrigir execução local

```text
Rode uma revisão do projeto e corrija qualquer erro que impeça `streamlit run app.py` de funcionar. Não altere o escopo do projeto. Corrija imports, nomes de módulos, dependências e chamadas quebradas.
```

## 2. Consolidar mock_data

```text
Revise `src/mock_data.py` e garanta que a função `load_mock_data()` retorne todos estes DataFrames: patients, treatment_plans, treatment_plan_items, execution_summary, appointments, appointment_items, patient_goals, weight_entries, satisfaction_entries, alerts e data_quality_issues. Garanta consistência de IDs entre tabelas.
```

## 3. Corrigir navegação por paciente

```text
Implemente ou corrija a navegação com `st.session_state` para que selecionar um paciente nas telas Pacientes, Visão Geral, Mapa de Decisão ou Alertas abra a página Ficha do Paciente com o paciente correto.
```

## 4. Melhorar Ficha do Paciente

```text
Melhore a página Ficha do Paciente mantendo o schema atual. Ela deve mostrar cabeçalho, KPIs do paciente, gráfico de peso esperado vs realizado, tabela de execução do plano, últimos agendamentos e alertas do paciente.
```

## 5. Melhorar Visão Geral

```text
Melhore a tela Visão Geral usando `st.columns`, `st.metric`, `st.container` e Plotly. A tela deve ficar clara para apresentação ao cliente, com dados fictícios e aviso discreto de que é uma casca navegável.
```

## 6. Melhorar Mapa de Decisão

```text
Melhore o Mapa de Decisão para exibir uma matriz 2x2 com os quatro quadrantes: Engajado + Satisfeito, Engajado + Não satisfeito, Não engajado + Satisfeito, Não engajado + Não satisfeito. Mostre chips/iniciais dos pacientes e permita abrir a ficha do paciente.
```

## 7. Melhorar Alertas

```text
Revise a tela Alertas para permitir filtro por categoria: Todos, Enfermagem, Médica, Comercial e Nutrição. Mostre prioridade, status, paciente, descrição e data. Permita abrir ficha do paciente.
```

## 8. Melhorar Qualidade dos Dados

```text
Melhore a tela Qualidade dos Dados para exibir score geral, barras de completude/consistência/validade/atualidade e uma tabela de lacunas. Inclua lacunas de peso, satisfação, objetivo e renovação.
```

## 9. Refatorar componentes

```text
Refatore componentes repetidos para `src/components`, especialmente cards de KPI, badges de status, tabela de alertas e cabeçalho de paciente. Não mude o comportamento visual sem necessidade.
```

## 10. Preparar README

```text
Atualize o README com: objetivo do projeto, como instalar, como rodar, estrutura de pastas, escopo da casca navegável, o que ainda não está implementado e próximos passos para integração com dados reais.
```

## 11. Revisão final antes de apresentar

```text
Faça uma revisão final da casca navegável. Garanta que todas as páginas abram, que a navegação funcione, que os dados mockados sejam coerentes e que não existam erros visíveis. Não implemente funcionalidades fora do escopo.
```
