# Estrutura de Repositório Esperada

```text
map-pacientes-streamlit/
  app.py
  requirements.txt
  README.md
  .gitignore

  data/
    mock/

  src/
    mock_data.py
    metrics.py
    quality.py
    navigation.py

    pages/
      visao_geral.py
      mapa_decisao.py
      pacientes.py
      ficha_paciente.py
      alertas.py
      atualizacao_dados.py
      qualidade_dados.py

    components/
      sidebar.py
      kpi_cards.py
      badges.py
      tables.py
      filters.py
      patient_header.py
      empty_states.py

    charts/
      weight_chart.py
      decision_map.py
      execution_chart.py

  docs/
    SPEC_CASCA_NAVEGAVEL_MAP_V1.md
```

## Observação

Se o Codex preferir criar alguns componentes a menos na primeira rodada, tudo bem, desde que:

```text
streamlit run app.py funcione
todas as páginas existam
dados mockados estejam centralizados
```

Não vale a pena travar a entrega por preciosismo de pasta.
