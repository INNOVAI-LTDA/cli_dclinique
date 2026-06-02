# Troubleshooting Streamlit + Codex

## Erro: módulo não encontrado

Prompt para Codex VS Code:

```text
Corrija os imports quebrados e ajuste a estrutura de pacotes para que `streamlit run app.py` funcione a partir da raiz do projeto.
```

## Erro: DataFrame sem coluna

Prompt:

```text
Revise os nomes das colunas usadas nesta página e alinhe com os DataFrames retornados por `load_mock_data()`. Não mude o schema sem atualizar todas as páginas.
```

## Erro: gráfico Plotly não renderiza

Prompt:

```text
Corrija o gráfico Plotly desta página. Garanta que os dados existam, que as colunas usadas estejam corretas e que `st.plotly_chart(..., use_container_width=True)` funcione.
```

## Erro: navegação não troca de página

Prompt:

```text
Corrija o uso de `st.session_state["page"]` e `st.session_state["selected_patient_id"]` para que a navegação entre Pacientes, Alertas, Mapa de Decisão e Ficha do Paciente funcione.
```

## Layout ficou ruim

Prompt:

```text
Melhore o layout visual usando Streamlit nativo: `st.columns`, `st.container`, `st.metric`, `st.tabs`, `st.dataframe`. Evite CSS excessivo.
```

## App depende de arquivo que não existe

Prompt:

```text
Remova dependências obrigatórias de arquivos externos reais. Esta versão deve funcionar apenas com dados mockados gerados em `src/mock_data.py`.
```

## Codex começou a implementar coisa fora do escopo

Prompt:

```text
Interrompa a implementação fora do escopo. Esta versão é apenas uma casca navegável com dados fictícios. Remova ou isole qualquer tentativa de Supabase, login, parser real, WhatsApp ou deploy.
```
