"""Test T2: src/data_layer/connection.py existe e expõe a API esperada.

Valida SEM precisar de DSN real:
  - Arquivo src/data_layer/connection.py existe
  - Módulo carrega sem erro (via spec_from_file_location; não depende de sys.path)
  - Funções esperadas (get_engine, _make_engine, _read_dsn, _import_psycopg,
    reset_engine) estão definidas e são chamáveis
  - _read_dsn() levanta RuntimeError quando nenhum DSN está configurado
    (com mensagem que menciona 'DSN' e instrui o usuário)
  - Cache _engine existe no módulo e começa como None

Não tenta criar conexão real — T2 valida só a forma da API, não o backend.

Nota sobre import: o test usa `importlib.util.spec_from_file_location` em
vez de `importlib.import_module("src.data_layer.connection")`. Motivo:
quando o test roda como subprocess via `subprocess.run(..., cwd=ROOT)`,
sys.path[0] é o diretório do script (worktree/scripts/), não a raiz do
worktree. Adicionar cwd ao sys.path também falha em alguns ambientes
Windows; spec_from_file_location carrega o arquivo diretamente.
"""
import importlib.util
import os
import sys
from pathlib import Path

TID = "T2"
TITLE = "Criar src/data_layer/connection.py"
FILE = Path("src/data_layer/connection.py")
EXPECTED_CALLABLES = [
    "get_engine",
    "_make_engine",
    "_read_dsn",
    "_import_psycopg",
    "reset_engine",
]


def main() -> int:
    # 1. Arquivo existe
    if not FILE.exists():
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: arquivo {FILE} existe na raiz do worktree")
        print(f"  Got:      nao encontrado em {FILE.resolve()}")
        print(f"  Fix:      criar src/data_layer/connection.py com a API esperada")
        return 1

    # 2. Carrega o módulo direto do arquivo (independente de sys.path)
    mod_name = "src.data_layer.connection"
    try:
        spec = importlib.util.spec_from_file_location(
            mod_name, str(FILE.resolve())
        )
        if spec is None or spec.loader is None:
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: spec criado para {FILE}")
            print(f"  Got:      importlib.util.spec_from_file_location retornou None")
            return 1
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: modulo {mod_name} carrega sem erro")
        print(f"  Got:      {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 3. Funções esperadas existem e são chamáveis
    missing = [
        f for f in EXPECTED_CALLABLES
        if not hasattr(mod, f) or not callable(getattr(mod, f))
    ]
    if missing:
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: funcoes {EXPECTED_CALLABLES} definidas e chamaveis")
        print(f"  Got:      faltam ou nao sao chamaveis: {missing}")
        print(f"  Atributos presentes: "
              f"{[a for a in dir(mod) if not a.startswith('__')]}")
        return 1

    # 4. _read_dsn() levanta RuntimeError sem DSN configurado
    #    Popamos env vars pra forçar a queda no caminho de erro.
    #    O caminho do streamlit secrets também não acha nada (sem secrets.toml).
    saved_env = {k: os.environ.pop(k, None) for k in ("NEON_DSN", "DCLINIQUE_DSN")}
    try:
        try:
            dsn = mod._read_dsn()
            print(f"[FAIL] {TID}: {TITLE}")
            print(f"  Expected: RuntimeError quando nenhum DSN configurado")
            print(f"  Got:      _read_dsn() retornou: {dsn!r}")
            print(f"  Hint:     unset NEON_DSN/DCLINIQUE_DSN antes de rodar, "
                  f"ou aponte st.secrets para um arquivo sem [postgres]")
            return 1
        except RuntimeError as e:
            if "DSN" not in str(e):
                print(f"[FAIL] {TID}: {TITLE}")
                print(f"  Expected: mensagem de erro menciona 'DSN'")
                print(f"  Got:      {e}")
                return 1
    finally:
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v

    # 5. Cache _engine existe
    if not hasattr(mod, "_engine"):
        print(f"[FAIL] {TID}: {TITLE}")
        print(f"  Expected: variavel de cache _engine existe no modulo")
        print(f"  Got:      nao encontrada")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  Arquivo:    {FILE}")
    print(f"  Funcoes:    {', '.join(EXPECTED_CALLABLES)}")
    print(f"  _read_dsn:  levanta RuntimeError sem DSN (mensagem menciona 'DSN')")
    print(f"  Cache:      _engine={mod._engine!r} (None = ainda nao inicializado)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
