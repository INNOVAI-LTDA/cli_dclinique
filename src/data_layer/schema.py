"""Schema management para o data layer Postgres (Neon).

Public API:
  - to_ddl(table, columns): str
        Constroi um `CREATE TABLE IF NOT EXISTS` a partir do nome da tabela
        e da lista de colunas. A primeira coluna vira PRIMARY KEY (TEXT,
        porque o id é surrogate tipo `pat_new_001`). As demais colunas
        ganham tipo inferido pelos maps abaixo.
  - init_schema(engine): None
        Aplica to_ddl para todas as 11 tabelas em EXPECTED_SCHEMAS.
        Idempotente: cada CREATE usa IF NOT EXISTS, então é seguro chamar
        no boot do app sem verificar se já existe.

Type mapping (espelha src/data_layer/csv_backend dtype maps):
  _DATE_COLUMNS          -> TIMESTAMP
  _BOOL_COLUMNS          -> BOOLEAN
  _NULLABLE_INT_COLUMNS  -> INTEGER
  _FLOAT_COLUMNS         -> DOUBLE PRECISION
  default                -> TEXT (incl. *_id surrogate, *_code, name, etc.)

Manter estes maps em sync com `src/data_layer/csv_backend.py:51-71` é
importante: se a coluna muda de tipo no CSV (ex.: age de int pra str),
o map aqui precisa refletir pra Postgres bater com o dtype do pandas.

Transitive imports:
  - src.schemas e' lazy (dentro de init_schema) para que carregar este
    modulo NAO puxe pandas via `src/schemas.py:4: import pandas as pd`.
    Carregar `src.data_layer.schema` continua funcionando sem pandas;
    apenas a chamada a init_schema() precisa de src.schemas.
"""
# NOTE: `from src.schemas import EXPECTED_SCHEMAS` foi movido para dentro
# de init_schema() (linha ~no final do arquivo). Carregar este modulo
# continua funcionando sem pandas instalado; a dependencia surge apenas
# quando o caller de fato precisa do catalogo de tabelas.


# (table, column) sets — mirrors csv_backend.py dtype maps
_DATE_COLUMNS = {
    ("patients", "created_at"),
    ("treatment_plans", "issue_date"),
    ("treatment_plans", "start_date"),
    ("treatment_plans", "end_date"),
    ("execution_summary", "plan_created_at"),
    ("appointments", "appointment_start"),
    ("appointments", "appointment_end"),
    ("appointment_items", "appointment_start"),
    ("patient_goals", "target_date"),
    ("weight_entries", "measurement_date"),
    ("satisfaction_entries", "date"),
    ("alerts", "created_at"),
}

_BOOL_COLUMNS = {
    ("treatment_plans", "is_renewal"),
    ("treatment_plan_items", "needs_manual_review"),
}

_NULLABLE_INT_COLUMNS = {
    ("patients", "age"),
    ("treatment_plan_items", "sessions_expected"),
    ("execution_summary", "sessions_expected"),
    ("execution_summary", "sessions_completed"),
    ("execution_summary", "sessions_remaining"),
    ("satisfaction_entries", "score"),
}

# CSV nao tem map explicito (pandas infere float64 automatico),
# mas Postgres precisa do tipo declarado.
_FLOAT_COLUMNS = {
    ("weight_entries", "weight"),
    ("patient_goals", "initial_weight"),
    ("patient_goals", "target_weight"),
}


def _postgres_type(table: str, column: str) -> str:
    """Resolve o tipo Postgres para (table, column). Default = TEXT."""
    key = (table, column)
    if key in _DATE_COLUMNS:
        return "TIMESTAMP"
    if key in _BOOL_COLUMNS:
        return "BOOLEAN"
    if key in _NULLABLE_INT_COLUMNS:
        return "INTEGER"
    if key in _FLOAT_COLUMNS:
        return "DOUBLE PRECISION"
    return "TEXT"


def to_ddl(table: str, columns: list) -> str:
    """Constroi um `CREATE TABLE IF NOT EXISTS` para a tabela.

    A primeira coluna em `columns` vira PRIMARY KEY TEXT (surrogate id
    tipo `pat_new_001`). As demais colunas recebem o tipo de
    `_postgres_type(table, col)`.
    """
    if not columns:
        raise ValueError(
            f"to_ddl({table!r}, []): columns deve ser nao-vazia"
        )

    pk = columns[0]
    col_lines = [f"  {pk} TEXT PRIMARY KEY"]
    for col in columns[1:]:
        pg_type = _postgres_type(table, col)
        col_lines.append(f"  {col} {pg_type}")

    return (
        f"CREATE TABLE IF NOT EXISTS {table} (\n"
        + ",\n".join(col_lines)
        + "\n);"
    )


def init_schema(engine) -> None:
    """Cria todas as 11 tabelas em EXPECTED_SCHEMAS se nao existirem.

    Idempotente. Cada CREATE usa `IF NOT EXISTS`, entao re-chamar e
    no-op quando as tabelas ja existem. Caller gerencia o lifecycle
    do engine (abrir/fechar).

    NAO usa `with engine:` -- em psycopg 3 o `__exit__` do
    Connection fecha a conexao ao sair (a menos que ela venha de
    um ConnectionPool). Como o data layer trata `engine` como
    long-lived por processo, qualquer `with engine:` quebra a
    proxima operacao com "the connection is closed". Como
    `autocommit=True` ja esta setado em connection._make_engine(),
    cada `cur.execute(ddl)` e' auto-committed; o context manager
    do engine nao e' necessario.

    O import de EXPECTED_SCHEMAS e' lazy (aqui dentro) para que o
    modulo `src.data_layer.schema` seja carregavel sem pandas; ver o
    comentario no topo do arquivo.
    """
    from src.schemas import EXPECTED_SCHEMAS  # lazy: pandas via src.schemas
    with engine.cursor() as cur:
        for table, columns in EXPECTED_SCHEMAS.items():
            ddl = to_ddl(table, columns)
            cur.execute(ddl)
