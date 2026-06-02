# Checklist de Validação Local

## 1. Preparar ambiente

### macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 2. Validar abertura

```text
[ ] App abriu no navegador.
[ ] Sidebar apareceu.
[ ] Não há traceback.
[ ] Não há erro de módulo.
```

## 3. Validar páginas

```text
[ ] Visão Geral.
[ ] Mapa de Decisão.
[ ] Pacientes.
[ ] Ficha do Paciente.
[ ] Alertas.
[ ] Atualização de Dados.
[ ] Qualidade dos Dados.
```

## 4. Validar navegação de paciente

```text
[ ] Selecionar paciente na tela Pacientes abre a ficha.
[ ] Selecionar paciente em Alertas abre a ficha.
[ ] Selecionar paciente no Mapa de Decisão abre a ficha.
[ ] A ficha troca corretamente de paciente.
```

## 5. Validar dados mockados

```text
[ ] Pelo menos 8 pacientes.
[ ] Há pacientes com alertas.
[ ] Há pacientes sem peso.
[ ] Há pacientes com renovação próxima.
[ ] Há pacientes com status variado.
[ ] Há execução de plano com previsto/realizado/restante.
```

## 6. Validar visual para apresentação

```text
[ ] Cards principais estão legíveis.
[ ] Tabelas não quebram layout.
[ ] Gráficos aparecem.
[ ] Badges/status são compreensíveis.
[ ] Existe indicação de dados fictícios.
```

## 7. Validar escopo

```text
[ ] Não há parser real implementado.
[ ] Não há credenciais.
[ ] Não há Supabase.
[ ] Não há dados sensíveis reais.
[ ] Não há dependência de arquivos externos obrigatórios.
```
