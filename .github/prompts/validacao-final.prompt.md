---
description: "Executa validação final com checklist de aceite antes do PR"
name: "Validação Final"
agent: "map-validacao"
argument-hint: "Opcional: focos extras de validação"
---
Você é responsável pela validação final antes de abrir PR.

Objetivo:
1) Validar que streamlit run app.py inicia sem erro.
2) Confirmar abertura de todas as páginas.
3) Validar fluxo de abertura da Ficha do Paciente a partir de Pacientes, Visão Geral, Mapa de Decisão e Alertas.
4) Confirmar coerência dos dados mockados e ausência de regressões visíveis.
5) Consolidar checklist final em aprovado ou reprovado.

Restrições obrigatórias:
- Não implementar funcionalidades fora do escopo.
- Não aceitar pendências sem indicar impacto.
- Entregar checklist objetivo com bloqueios para PR, se houver.
