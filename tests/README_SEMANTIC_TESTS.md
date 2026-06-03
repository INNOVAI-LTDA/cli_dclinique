# 🧪 Suíte de Testes Semânticos e de Runtime do Streamlit

## Visão Geral

Esta nova bateria de testes foi criada para detectar **erros fundamentais de semântica, sintaxe e uso correto da API do Streamlit**, complementando os testes funcionais existentes.

## Arquivos Criados

### 1. `tests/test_streamlit_semantics.py` (12 testes)
Validação estática do código fonte para detectar problemas de:
- **Uso incorreto da API do Streamlit** (parâmetros inválidos)
- **Sintaxe Python** (erros de compilação)
- **Operações com DataFrame** (seleção de colunas)
- **Estrutura das páginas** (funções render)

#### Classes de Teste:
| Classe | Descrição | Testes |
|--------|-----------|--------|
| `TestStreamlitAPIUsage` | Valida parâmetros de `st.dataframe()` e `st.plotly_chart()` | 4 |
| `TestPythonSyntaxAndSemantics` | Verifica sintaxe, except genéricos e imports | 3 |
| `TestDataFrameOperations` | Valida seleções de colunas em DataFrames | 2 |
| `TestPageRenderFunctions` | Garante estrutura correta das páginas | 2 |
| `TestComponentConsistency` | Verifica consistência dos componentes | 1 |

### 2. `tests/test_streamlit_runtime.py` (7 testes)
Testes de integração que **simulam execução real** com Streamlit mockado:

#### Classes de Teste:
| Classe | Descrição | Testes |
|--------|-----------|--------|
| `TestPageExecutionWithMockedStreamlit` | Executa páginas com mocks validadores | 3 |
| `TestDataFrameColumnSelection` | Testa seleções de colunas para evitar KeyError | 2 |
| `TestComponentFunctionSignatures` | Valida importação de componentes | 1 |
| `TestChartGeneration` | Verifica existência de funções de gráficos | 1 |

## Principais Validações

### 🔍 Detecção de Erros de API

```python
# ❌ ERRO DETECTADO: width=None
st.dataframe(df, width=None)  # ValueError no teste

# ✅ CORRETO:
st.dataframe(df, width="stretch")
st.dataframe(df, use_container_width=True)
```

### 📊 Validação de Parâmetros

Os testes verificam se os parâmetros `width` em `st.dataframe()` e `st.plotly_chart()` são:
- `"stretch"` (padrão)
- `"content"`
- Um inteiro positivo (pixels)

### 🛡️ Prevenção de KeyError

Verifica se todas as colunas selecionadas em DataFrames existem:
```python
# ❌ ERRO DETECTADO: coluna inexistente
df[["coluna_que_nao_existe"]]

# ✅ TESTE GARANTE: colunas válidas
columns = ["Procedimento", "Previsto", "Realizado"]
assert all(col in df.columns for col in columns)
```

### 🏗️ Estrutura das Páginas

Garante que todas as páginas:
- Têm uma função `render(data)`
- Aceitam o parâmetro `data`
- Podem ser importadas sem erros

## Como Executar

```bash
# Executar todos os testes (55 testes no total)
cd /workspace && python -m pytest tests/ -v

# Executar apenas testes semânticos
cd /workspace && python -m pytest tests/test_streamlit_semantics.py -v

# Executar apenas testes de runtime
cd /workspace && python -m pytest tests/test_streamlit_runtime.py -v

# Executar com detalhes de erro
cd /workspace && python -m pytest tests/ -v --tb=short

# Executar com cobertura de código (se coverage estiver instalado)
cd /workspace && python -m pytest tests/ --cov=src --cov-report=html
```

## Resultados Atuais

```
============================== 55 passed in 3.85s ==============================
```

✅ **Todos os 55 testes passaram!**

### Distribuição dos Testes

| Categoria | Quantidade | Status |
|-----------|------------|--------|
| Testes Originais (`test_pages_loading.py`) | 36 | ✅ Pass |
| Testes Semânticos (`test_streamlit_semantics.py`) | 12 | ✅ Pass |
| Testes de Runtime (`test_streamlit_runtime.py`) | 7 | ✅ Pass |
| **TOTAL** | **55** | **✅ Pass** |

## Benefícios Desta Abordagem

### 1. **Detecção Precoce de Erros**
- Erros de API são detectados antes da execução no Streamlit
- Problemas de sintaxe são pegos na análise estática

### 2. **Validação de Contratos**
- Garante que todas as páginas seguem o mesmo padrão
- Valida estrutura de dados esperada

### 3. **Resiliência a Mudanças**
- Se alguém adicionar `width=None` acidentalmente, o teste falha
- Se uma coluna for renomeada, o teste de seleção detecta

### 4. **Documentação Viva**
- Os testes documentam o comportamento esperado
- Novos desenvolvedores entendem as regras pelo código dos testes

## Exemplo de Uso do Mock Validador

```python
# O mock valida parâmetros automaticamente
def validate_dataframe(*args, **kwargs):
    width = kwargs.get("width", "stretch")
    if width is None:
        raise ValueError("Invalid width value: None...")
    return MagicMock()

mock_dataframe.side_effect = validate_dataframe
```

## Próximos Passos Sugeridos

1. **CI/CD Integration**: Adicionar estes testes no pipeline de CI
2. **Pre-commit Hook**: Rodar testes semânticos antes de cada commit
3. **Expansão**: Adicionar mais validações específicas do domínio
4. **Performance Tests**: Medir tempo de carregamento das páginas

---

**Status**: ✅ Todos os testes passando  
**Cobertura**: Sintaxe, semântica, API do Streamlit, imports, estrutura de páginas  
**Tempo de Execução**: ~4 segundos para 55 testes
