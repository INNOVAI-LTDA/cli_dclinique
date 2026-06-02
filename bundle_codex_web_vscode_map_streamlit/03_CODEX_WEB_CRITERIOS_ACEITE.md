# Critérios de Aceite — Entrega do Codex Web

Use este checklist antes de levar o projeto para ajustes finos no VS Code.

## Execução

```text
[ ] O repositório tem `app.py`.
[ ] O repositório tem `requirements.txt`.
[ ] `pip install -r requirements.txt` funciona.
[ ] `streamlit run app.py` funciona.
[ ] O app abre no navegador.
[ ] Não há erro de importação.
[ ] Não há erro de módulo inexistente.
```

## Estrutura

```text
[ ] Existe pasta `src/`.
[ ] Existe pasta `src/pages/`.
[ ] Existe pasta `src/components/`.
[ ] Existe pasta `src/charts/`.
[ ] Existe `src/mock_data.py`.
[ ] Existe README com instruções.
```

## Dados

```text
[ ] `load_mock_data()` existe.
[ ] Retorna todos os DataFrames esperados.
[ ] Existem pelo menos 8 pacientes fictícios.
[ ] Existem cenários variados: engajado, não engajado, satisfeito, insatisfeito, renovação próxima, sem peso, manipulado pendente.
[ ] Os nomes dos campos são consistentes entre telas.
```

## Navegação

```text
[ ] Sidebar renderiza.
[ ] Visão Geral abre.
[ ] Mapa de Decisão abre.
[ ] Pacientes abre.
[ ] Ficha do Paciente abre.
[ ] Alertas abre.
[ ] Atualização de Dados abre.
[ ] Qualidade dos Dados abre.
[ ] Selecionar paciente atualiza a ficha.
```

## Visual

```text
[ ] Cards de KPI aparecem.
[ ] Tabelas aparecem.
[ ] Gráficos aparecem.
[ ] Alertas têm categorias.
[ ] Layout usa `wide`.
[ ] Há mensagem informando que dados são fictícios.
```

## O que pode ficar para VS Code

```text
[ ] Ajustes de espaçamento.
[ ] Melhorias visuais.
[ ] Correções pequenas de estado.
[ ] Refatorações.
[ ] Melhoria dos gráficos.
[ ] Ajuste de componentes.
```
