# Catálogo de Exceções por Lib

> **Propósito:** documentar, **antes de escrever código**, quais exceções cada lib usada pelo `src/core/` pode levantar, qual a mensagem em PT-BR correspondente, e onde aplicar o `try/except`.
>
> **Regra (N7):** toda chamada a uma lib que aparece neste catálogo **deve** estar envolvida em `try/except` específico (não bare) com a mensagem traduzida listada aqui. Se a lib não está no catálogo, a chamada não pode ser adicionada sem antes atualizar este arquivo.
>
> **Status:** esqueleto populado para Fase 1 (pandas, pathlib, datetime, dataclasses, typing). Demais libs (psycopg, streamlit, dateutil, ruff/pytest) serão preenchidas nas fases correspondentes.
>
> **Fontes consultadas para esta versão:**
> - pandas: https://pandas.pydata.org/docs/reference/errors.html
> - Python stdlib (pathlib, datetime, dataclasses): https://docs.python.org/3/library/exceptions.html

---

## 1. `pandas` (uso em `repos.py`, `mapping.py`, `csv_importer/*`)

### 1.1. Operações usadas neste projeto

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `pd.read_csv(path)` | `csv_importer/*`, conftest | `pd.errors.EmptyDataError`, `pd.errors.ParserError`, `UnicodeDecodeError`, `OSError` |
| `df.iterrows()` | `mapping.py`, `repos.py` | (nenhuma — sempre OK se DataFrame existe) |
| `df.itertuples()` | (alternativa a iterrows, mais rápida) | (nenhuma) |
| `df[col]` / `df.get(col)` | `mapping.py` | `KeyError` (em `df[col]`) |
| `row.get("col")` | `mapping.py` | (nenhuma — `get` é seguro) |
| `pd.to_numeric(series, errors="coerce")` | `mapping.py` | (nenhuma — `errors="coerce"` transforma inválidos em `NaN`) |
| `pd.to_datetime(series, errors="coerce")` | `mapping.py` | (nenhuma — `errors="coerce"` transforma inválidos em `NaT`) |
| `df.groupby(...).agg(...)` | `metrics.py` (existente) | `KeyError`, `ValueError` |
| `df.merge(...)` | `metrics.py` (existente) | `KeyError`, `ValueError` (colunas ambíguas) |
| `df.sort_values(...)` | `mapping.py` | `KeyError` (coluna inexistente) |
| `df.fillna(...)` | (nenhuma — operação segura) | (nenhuma) |
| `df.dropna(subset=[...])` | (operação segura) | `KeyError` (subset inválido) |

### 1.2. Exceções — referência rápida

| Exceção | Causa típica | Onde capturar | Mensagem PT-BR |
|---|---|---|---|
| `pd.errors.EmptyDataError` | CSV sem linhas ou só cabeçalho | fronteira `csv_importer/*.py` | "Arquivo CSV vazio ou sem dados: {path}. Verifique se o arquivo foi exportado corretamente." |
| `pd.errors.ParserError` | CSV malformado (delimitador errado, aspas quebradas) | fronteira `csv_importer/*.py` | "Não foi possível ler o CSV {path}. Verifique o delimitador e o encoding." |
| `UnicodeDecodeError` | Encoding errado (latin1 em vez de utf-8) | fronteira `csv_importer/*.py` | "Encoding do arquivo {path} não é UTF-8. Tentando latin1 automaticamente." |
| `KeyError` | Coluna esperada ausente no DataFrame | **fronteira `mapping.py`** | "Coluna obrigatória '{col}' ausente na tabela {tabela}. Esperado: {colunas_esperadas}." |
| `ValueError` (em `merge`/`groupby`) | Colunas ambíguas ou tipo incompatível | **fronteira `mapping.py`** | "Conflito de colunas ao processar {tabela}: verifique se os nomes são únicos." |

### 1.3. Forma canônica de captura em `mapping.py`

```python
try:
    return pd.to_numeric(row["cpf"], errors="coerce")
except KeyError:
    _log.error(
        "Coluna 'cpf' ausente na tabela clients — esperado pelas schemas em src/schemas.py."
    )
    return None
```

---

## 2. `pathlib` (uso em `repos.py`, `csv_importer/*`)

### 2.1. Operações usadas

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `Path(path).read_text(encoding="utf-8")` | `csv_importer/*` | `FileNotFoundError`, `PermissionError`, `UnicodeDecodeError` |
| `Path(path).open("r", encoding="utf-8")` | (alternativa) | mesmas |
| `Path(path).exists()` | (verificação) | `OSError` (caminho inválido no Windows) |
| `Path(path).iterdir()` | listagem | `FileNotFoundError`, `PermissionError`, `OSError` |

### 2.2. Exceções — referência rápida

| Exceção | Causa típica | Mensagem PT-BR |
|---|---|---|
| `FileNotFoundError` | Arquivo não existe no caminho | "Arquivo não encontrado: {path}. Verifique se o caminho está correto." |
| `PermissionError` | Sem permissão de leitura | "Sem permissão para ler o arquivo: {path}. Contate o administrador." |
| `OSError` | Caminho inválido (Windows: `\\?\`, drive inexistente) | "Caminho inválido: {path}. Verifique a estrutura de diretórios." |

---

## 3. `datetime` (uso em `types.py`, `frequency.py`)

### 3.1. Operações usadas

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `date.fromisoformat("YYYY-MM-DD")` | `mapping.py` (parser de `data_inicio`) | `ValueError` |
| `date.today()` | `frequency.py` | (nenhuma) |
| `(d1 - d2).days` | `frequency.py` | `TypeError` (se um for `None`) |
| `datetime.fromisoformat("YYYY-MM-DDTHH:MM:SS")` | `mapping.py` | `ValueError` |

### 3.2. Exceções — referência rápida

| Exceção | Causa típica | Mensagem PT-BR |
|---|---|---|
| `ValueError` (em `fromisoformat`) | String fora do formato ISO | "Data inválida: {value}. Esperado formato YYYY-MM-DD." |
| `TypeError` (em subtração) | `None` em uma das datas | "Data obrigatória ausente. Verifique se o cadastro do cliente está completo." |

---

## 4. `dataclasses` (uso em `types.py`)

### 4.1. Operações usadas

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `@dataclass(frozen=True)` | `types.py` | (nenhuma em decoradores) |
| `Client(id=1, nome="Maria", cpf=None, ...)` | `mapping.py` | `TypeError` (campo obrigatório faltando) |

### 4.2. Exceções — referência rápida

| Exceção | Causa típica | Mensagem PT-BR |
|---|---|---|
| `TypeError` (instanciação) | Campo obrigatório sem default não foi passado | "Campo obrigatório '{field}' ausente ao criar {ClassName}." |
| `FrozenInstanceError` | Tentativa de `client.id = 2` em `frozen=True` | "Tentativa de alterar atributo de {ClassName} (frozen=True). Crie uma nova instância." |

---

## 5. `typing` (uso geral)

### 5.1. Operações usadas

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `Literal["Provider", "Admin"]` | `types.py:User.tipo` | `TypeError` (em runtime) se valor fora do literal |
| `Optional[X]` / `X \| None` | `types.py` | (apenas type hints — não runtime) |

### 5.2. Exceções — referência rápida

| Exceção | Causa típica | Mensagem PT-BR |
|---|---|---|
| `TypeError` (em runtime, validar `Literal`) | Valor fora do conjunto esperado | "Valor inválido para {field}: {value}. Esperado um de: {literals}." |

> **Nota:** em Python, `Literal` não valida em runtime por padrão. Para validar, usar `typing.get_args()` ou `typing.get_type_hints()`. Em `mapping.py`, adicionar assertion:
> ```python
> if row["tipo"] not in ("Provider", "Admin"):
>     raise ValueError(f"Tipo de usuário inválido: {row['tipo']!r}")
> ```

---

## 6. `pytest` (uso em `tests/`)

### 6.1. Operações usadas

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `pytest.raises(ExceptionType)` | `tests/test_exception_handling.py` | (intencional — captura para validar) |
| `pytest.fixture` | `tests/conftest.py` | `FixtureLookupError` |
| `pytest.mark.parametrize` | `tests/test_core_*.py` | `pytest.PytestUnknownMarkWarning` (warning, não erro) |

> **Não precisa try/except** — exceptions em testes são esperadas e fazem parte do ciclo.

---

## 7. `ruff` (uso em script)

CLI tool, não Python. Sem exceções no sentido tradicional. **Exit codes:**
- `0`: OK
- `1`: encontrou violações
- `2`: erro de configuração

O script `run_core_tests.ps1` traduz:
```powershell
if ($LASTEXITCODE -ne 0) {
    Write-Error "ruff check falhou com exit $LASTEXITCODE. Veja logs/test_core_<ts>.log"
    exit 1
}
```

---

## 8. `src.data_layer.append_row` (uso em `persistence.py`, Fase 3)

`persistence.py:save_frequency_alerts` e' a unica boundary function que
chama `data_layer.append_row('alerts', row)` para persistir alertas de
frequencia. A funcao e' boundary (N7 E6): captura TODAS as excecoes da
fronteira I/O e loga em PT-BR, retornando a contagem efetiva ao caller.

### 8.1. Operações usadas neste projeto

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `data_layer.append_row(table, row)` | `persistence.py:save_frequency_alerts` | `FileNotFoundError` (csv ausente), `PermissionError` (read-only), `OSError` (disco cheio, path invalido), `ValueError` (schema check), `TypeError` (tipo errado), `KeyError` (coluna faltando — defensivo) |
| `data_layer.load_all()` | `persistence.py:save_frequency_alerts` (1 leitura para check de dedup) | delegadas ao backend (csv_backend ou postgres_backend) |

### 8.2. Exceções — referência rápida

| Exceção | Causa típica | Onde capturar | Mensagem PT-BR |
|---|---|---|---|
| `FileNotFoundError` | Pasta `data/csv/` nao existe; CSV removido mid-run | `persistence.py:save_frequency_alerts` | "Arquivo de alertas nao encontrado ao salvar {alert_id}: {exc}. Verifique se a pasta de dados existe." |
| `PermissionError` | FS read-only (chmod 444); SELinux deny | `persistence.py:save_frequency_alerts` | "Sem permissao para escrever alertas ({alert_id}): {exc}. Contate o administrador do sistema." |
| `OSError` | Disco cheio; path invalido (Windows: `\\?\`, drive inexistente) | `persistence.py:save_frequency_alerts` | "Erro de I/O ao salvar alerta {alert_id}: {exc}. Verifique o disco e tente novamente." |
| `ValueError` | Schema check falhou (coluna faltando, tipo errado) | `persistence.py:save_frequency_alerts` | "Dados invalidos ao salvar alerta {alert_id}: {exc}. Verifique se o alerta tem todos os campos do schema." |
| `TypeError` | Dict tem chave nao-string ou valor de tipo incompativel | `persistence.py:save_frequency_alerts` | (mesma de ValueError — capturadas juntas) |
| `KeyError` | (defensivo — improvavel em runtime) | `persistence.py:save_frequency_alerts` | (mesma de ValueError — capturadas juntas) |

### 8.3. Forma canônica de captura em `persistence.py`

```python
try:
    append_row("alerts", alert_dict)
except FileNotFoundError as exc:
    logger.error(
        "Arquivo de alertas nao encontrado ao salvar %s: %s. "
        "Verifique se a pasta de dados existe.",
        alert_id, exc,
    )
    failed += 1
    continue
except PermissionError as exc:
    logger.error(
        "Sem permissao para escrever alertas (%s): %s. "
        "Contate o administrador do sistema.",
        alert_id, exc,
    )
    failed += 1
    continue
# ... OSError, ValueError, TypeError, KeyError
```

### 8.4. Por que `persistence.py` e' boundary e `alerts.py` e' pura

* `alerts.detect_frequency_alerts(...)` recebe dados ja' validados pelo caller
  (CD vindo de `repos.py`, sessions vindas de `repos.py`). Erros de tipo sao
  detectados via guard no inicio (`isinstance(as_of, date)`) ou deixados
  subir como `TypeError`/`ValueError` nativo. Funcao pura (N7 E5).
* `persistence.save_frequency_alerts(...)` e' o UNICO ponto que toca
  `data_layer.append_row` (I/O real). Por isso captura e traduz. Boundary
  (N7 E6).

### 8.5. Compatibilidade Postgres (Fase 8)

`data_layer.append_row` ja' tem uma implementacao Postgres espelhada em
`src/data_layer/postgres_backend.py` (mesma assinatura, mesmas excecoes
esperadas: `psycopg.errors.UniqueViolation`, `OperationalError`, etc.).
Quando a Fase 8 migrar `persistence.py` para o backend Postgres, este
catalogo devera' ser atualizado para listar as excecoes especificas do
`psycopg` em uma sub-tabela (mesmo padrao da §7 do caminho_b_plano.md).

---

## 11. `pandas.read_csv` + `pd.to_datetime(format=...)` (uso em `src/csv_importer/`, Fase 6)

O importador CSV (Caminho B, Fase 6) le 2 CSVs de exportacao do IClinic
(`data/new/Relatorio de frequencia.csv` e `data/new/Agendamentos.csv`)
e produz v1 rows para `treatment_plans`, `treatment_plan_items`,
`execution_summary`, `appointments` e `appointment_items`.

### 11.1. Operações usadas neste projeto

| Operação | Onde aparece | Exceções possíveis |
|---|---|---|
| `pd.read_csv(path, dtype=str, keep_default_na=False)` | `parse_frequencia_csv`, `parse_agendamentos_csv` | `FileNotFoundError`, `PermissionError`, `OSError`, `pd.errors.EmptyDataError`, `pd.errors.ParserError`, `UnicodeDecodeError` |
| `pd.to_datetime(value, format="%d/%m/%Y", errors="coerce")` | `parse.parse_br_date`, `parse.parse_br_datetime` | (nenhuma — `errors="coerce"` retorna `NaT`) |
| `pd.to_datetime(value, format="%d/%m/%Y %H:%M:%S", errors="raise")` | `parse.parse_br_datetime` (formato com segundos) | `ValueError`, `TypeError` (formato incompativel) — capturadas e cai no proximo formato |
| `df.iterrows()` | iteracao sobre linhas CSV em `parse_*_csv` | (nenhuma — iterrows sempre retorna tuplas se df existe) |
| `row["col"]` (Series) | acesso a coluna do CSV | `KeyError` (coluna nao existe) — defensivo com try/except |
| `df["col1"] == target` (Series comparison) | `dedup.find_patient_by_name` | `TypeError`, `ValueError` (tipo incompativel) — defensivo |

### 11.2. Exceções — referência rápida

| Exceção | Causa típica | Onde capturar | Mensagem PT-BR |
|---|---|---|---|
| `FileNotFoundError` | Path do CSV nao existe | `parse_*_csv` (boundary) | "Arquivo de {frequencia/agendamentos} nao encontrado: {path}. Verifique se o CSV foi exportado para a pasta correta." |
| `PermissionError` | Sem permissao de leitura no arquivo | `parse_*_csv` (boundary) | "Sem permissao para ler o arquivo: {path}. Contate o administrador." |
| `OSError` | Caminho invalido no Windows, mid-run delete | `parse_*_csv` (boundary) | "Erro de I/O ao ler CSV: {exc}. Verifique o disco e o caminho." |
| `pd.errors.EmptyDataError` | CSV sem linhas ou so' header | `parse_*_csv` (boundary) | "Arquivo CSV vazio ou sem dados: {path}. Verifique se o arquivo foi exportado corretamente." |
| `pd.errors.ParserError` | CSV malformado (delimitador errado, aspas quebradas) | `parse_*_csv` (boundary) | "Nao foi possivel ler o CSV {path}. Verifique o delimitador e o encoding." |
| `UnicodeDecodeError` | Encoding errado (latin1 em vez de utf-8) | `parse_*_csv` (boundary) | "Encoding do arquivo {path} nao e' UTF-8. Verifique se o CSV foi exportado com encoding UTF-8." |
| `ValueError` (em `to_datetime` com `format=...` + `errors="raise"`) | String fora do formato esperado | `parse.parse_br_datetime` (loop de formatos) | (nao levanta — o loop cai no proximo formato) |
| `TypeError` (em `to_datetime` com `format=...` + `errors="raise"`) | Tipo incompativel (e.g. None) | `parse.parse_br_datetime` | (nao levanta — cai no proximo formato) |
| `KeyError` (em `row["col"]`) | Coluna CSV ausente | `parse_*_csv` | "CSV de {frequencia/agendamentos} sem coluna(s) obrigatoria(s): {missing}. Esperado: {required}." |

### 11.3. Forma canonica de captura em `parse_*_csv`

```python
try:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
except FileNotFoundError as exc:
    raise CsvImportError(
        f"Arquivo do relatorio de frequencia nao encontrado: {path!s}"
    ) from exc
except PermissionError as exc:
    raise CsvImportError(
        f"Sem permissao para ler o relatorio de frequencia: {path!s}"
    ) from exc
except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
    raise CsvImportError(
        f"Falha ao parsear CSV de frequencia: {exc}"
    ) from exc
except OSError as exc:
    raise CsvImportError(
        f"Erro de I/O ao ler CSV de frequencia: {exc}"
    ) from exc
```

`CsvImportError` e' a excecao de dominio re-emitida pelas 2 funcoes
boundary (`parse_frequencia_csv` e `parse_agendamentos_csv`). Herda de
`RuntimeError` (nao de `OSError`/`ValueError`) para deixar claro que
e' uma excecao de fronteira, nao do pandas.

### 11.4. Por que **nao** usamos `dateutil`

O brief original do plano (§3 Fase 6) mencionou "dateutil (parser de
data BR)". A implementacao atual usa `pd.to_datetime(value, format=..., errors="coerce")`
e `pd.to_datetime(value, format=..., errors="raise")` com formatos
explicitos (`%d/%m/%Y`, `%d/%m/%Y %H:%M:%S`, etc.). Motivos:

  1. **Cobertura total dos formatos do IClinic** — os CSVs usam 3
     formatos deterministicos; cobrir via loop de `format=` e' mais
     previsivel que deixar o dateutil inferir.
  2. **Sem dep nova** — `dateutil` ja' vem como dependencia transitiva
     do pandas, mas adicionar `import dateutil` explicito e' uma
     superficie de API a mais. `pd.to_datetime` ja' da' conta.
  3. **Erro tipado** — `format=` invalido gera `ValueError`/`TypeError`
     capturavel no loop; `dateutil.parser.parse` levanta
     `dateutil.parser.ParserError` que exigiria nova entrada neste
     catalogo.

Se Fase 7 precisar de parser mais tolerante (e.g. "amanha", "hoje",
datas em portugues natural), a §11.4 sera' revisada e `dateutil`
entrara' no catalogo.

### 11.5. Compatibilidade Postgres (Fase 8)

`pd.read_csv` nao sera' usado quando o backend Postgres estiver ativo
em PRD — os dados v2 vem direto de `SELECT *` em
`postgres_backend.py`. Esta §11 aplica-se apenas ao modo dev offline
(`DCLINIQUE_BACKEND=csv`) e ao wizard de import (que escreve no backend
ativo, mas le o CSV do disco sempre).

---

## 9. Libs a serem adicionadas em fases posteriores

| Fase | Lib | Operações previstas | Status do catálogo |
|---|---|---|---|
| 0 | (nenhuma nova) | setup de infra | vazio |
| 1 | pandas, pathlib, datetime, dataclasses | tipos + repos | **preenchido** (§1-5) |
| 2 | (nenhuma nova — usa pandas) | frequency | vazio |
| 3 | data_layer.append_row | alerts + persistence | **preenchido** (§8) |
| 4 | streamlit | render Mapa de Decisão | **a preencher na Fase 4** |
| 5 | streamlit | render Alertas | já em Fase 4 |
| 6 | pandas (read_csv), pd.to_datetime (parser de data BR) | csv_importer | **preenchido** (§11) |
| 7 | (nenhuma nova) | e2e | vazio |
| 8 | psycopg | persistência v2 | **a preencher na Fase 8 (se chegar)** |

---

## 10. Procedimento para adicionar uma nova lib

1. **Consultar a documentação oficial** da lib (link no início de cada seção).
2. **Listar as operações** que serão usadas em `src/core/`.
3. **Listar as exceções possíveis** para cada operação (não listar "todas", só as realistas).
4. **Mapear para mensagem PT-BR** — escrever como você explicaria para o cliente, não como o dev entenderia.
5. **Atualizar este catálogo** com uma nova sub-seção (§X).
6. **Atualizar `requirements-dev.txt`** (ou `requirements.txt`) com a lib + versão pinada.
7. **Rodar o script** — o `tests/test_exception_handling.py` precisa ser atualizado para validar a nova lib.

Se a lib tem exceções muito específicas (ex.: `psycopg.errors.UniqueViolation` vs `psycopg.IntegrityError`), criar sub-tabela.

---

## 11. Auditoria

A cada fim de fase, o diff de `src/core/` é cruzado com este catálogo:

```bash
# Lista todos os imports de src/core/
grep -rh "^from \|^import " src/core/ | sort -u

# Lista todas as chamadas externas (não-stdlib, não dataclasses, não typing)
# (heurística — refinada pelo linter)
grep -rhE "\b(pd|psycopg|streamlit|dateutil|plotly)\." src/core/ | sort -u
```

Cada chamada deve ter correspondência em uma seção deste catálogo. Se não tem, **bloqueia o PR** até atualizar.

---

## 12. MVP Jornada Clínica (2026-06-30) — `openpyxl`

> **Origem:** Reunião Diego + Jader em 2026-06-30 21:25 (ata em `docs/cliente_reuniao_2026-06-30.md`). Decisão D1+D2+D7 + §5+§8.4 da ata exigem parser de Excel para agendamentos. Excel parser foi promovido a **exceção do Cliente** em CLAUDE.md (2026-06-30, M1 da execução autorizada).

**Status:** rascunho — preenchido quando a Fase 3 (`excel_importer`) entrar em desenvolvimento.

### 12.1 Operações previstas

| Operação | Onde vai ser usada | Exceções a capturar |
|---|---|---|
| `openpyxl.load_workbook(path)` | `src/excel_importer/parse.py` | `openpyxl.utils.exceptions.InvalidFileException`, `FileNotFoundError`, `PermissionError`, `zipfile.BadZipFile` |
| `ws.iter_rows(values_only=True)` | `src/excel_importer/parse.py` | (genérico) — capturar `StopIteration` apenas se necessário |
| `cell.value` (data type coercion) | `src/excel_importer/parse.py` | `TypeError`, `ValueError` para datas PT-BR |
| `wb.save(path)` | (somente se houver write-back; verificar antes) | `PermissionError` |

### 12.2 Exceções específicas com mensagem PT-BR

| Exceção | Mensagem PT-BR |
|---|---|
| `openpyxl.utils.exceptions.InvalidFileException` | "Arquivo Excel inválido ou corrompido: {path}. Verifique se é um .xlsx legítimo." |
| `zipfile.BadZipFile` | "Arquivo Excel inválido (não é um arquivo .xlsx válido): {path}." |
| `FileNotFoundError` | "Arquivo Excel não encontrado: {path}." |
| `PermissionError` | "Sem permissão para ler o arquivo Excel: {path}." |
| `KeyError` (coluna faltando no header) | "Coluna obrigatória ausente no Excel: {coluna}. Esperado: {schema}." |

### 12.3 Notas de design

- **`openpyxl` é lazy** — importar dentro da função `parse_xlsx()`, não no topo do módulo. Preserva cold start (CLAUDE.md seção "Otimizações ativas").
- **Datas no Excel**: serial number nativo do Excel; converter via `openpyxl.utils.datetime.from_excel` ou detectar se é string PT-BR (`DD/MM/YYYY`). **Validar com 1 amostra de Jader antes de fixar a heurística.**
- **Encoding**: Excel `.xlsx` é XML interno UTF-8; não há problema de mojibake. Mas se vier CSV em vez de XLSX, aplicar pattern do §1 (UnicodeDecodeError).
- **Não usar** `xlrd` (legado, não lê `.xlsx`). **Não usar** `pandas.read_excel` para .xlsx sem ter `openpyxl` ou `xlrd` instalado — usar `openpyxl` direto é mais transparente.

---

## 13. MVP Jornada Clínica (2026-06-30) — pandas aplicado ao Excel

> `pandas.read_excel` **NÃO** será usado (mais lento, menos transparente que `openpyxl` direto). Mas `pandas` continua sendo usado em todo o resto do MVP (criação de DataFrames para `expected_appointments`, `alerts`, etc.). Exceções de `pandas` já estão catalogadas nas seções §1, §6 e §11 deste catálogo (Caminho B). **Não duplicar.**

---

## 14. MVP Jornada Clínica (2026-06-30) — psycopg (já catalogado em §8 do Caminho B)

> `psycopg` (Neon backend) já está coberto pela §8 (catalog original do Caminho B). O MVP herda sem alterações: `INSERT ... ON CONFLICT` para idempotência, `connection.timeout` para não travar UI, `pool de conexões` para jobs recorrentes (Fase 8).
