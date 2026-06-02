# Prompt Curto para Continuação

Use este prompt quando já houver código gerado:

```text
Estamos construindo uma casca navegável em Streamlit para o MAP de Acompanhamento de Pacientes.

Escopo:
- dados fictícios;
- schema compatível com banco futuro;
- navegação entre telas;
- ficha do paciente;
- visual pronto para validação.

Não implementar:
- parser real;
- Supabase;
- login;
- deploy;
- WhatsApp;
- Google Drive.

Antes de alterar, leia app.py, src/mock_data.py e as páginas existentes. Mantenha o schema dos DataFrames consistente. Priorize fazer `streamlit run app.py` funcionar sem erros.
```
