"""One-shot bootstrap: cria as 11 tabelas no Neon Postgres.

Uso:
    DCLINIQUE_BACKEND=postgres python scripts/init_neon_schema.py

Le o DSN de ``st.secrets["postgres"]["dsn"]`` ou das env vars
``NEON_DSN`` / ``DCLINIQUE_DSN`` (via
:func:`src.data_layer.connection.get_engine`). Chama
:func:`src.data_layer.schema.init_schema` que itera as 11 tabelas
em ``EXPECTED_SCHEMAS`` e executa ``CREATE TABLE IF NOT EXISTS`` para
cada uma.

Idempotente: cada ``CREATE`` usa ``IF NOT EXISTS``, entao re-chamar
e' no-op quando as tabelas ja existem. Rode uma vez apos provisionar
o projeto Neon; rode novamente com seguranca para confirmar.

Exit codes:
  0 — todas as 11 tabelas criadas (ou ja existiam)
  1 — DSN nao configurado (RuntimeError de ``get_engine``)
  2 — ``init_schema`` falhou (ex.: DB inacessivel, permissao negada)

Transitive imports (todos lazy):
  - :mod:`psycopg`, :mod:`streamlit`, :mod:`src.schemas` sao lazy
    dentro de ``connection.get_engine`` / ``schema.init_schema``.
    Carregar este script NAO dispara conexao nem importa pacotes
    pesados. A primeira query acontece quando ``init_schema`` e'
    chamado.
"""
from __future__ import annotations

import sys

from src.data_layer.connection import get_engine
from src.data_layer.schema import init_schema


def main() -> int:
    """Bootstrap one-shot. Retorna exit code (0 = sucesso)."""
    try:
        engine = get_engine()
    except RuntimeError as e:
        # DSN nao configurado. Mensagem do connection.py ja e' acionavel;
        # adicionamos prefixo para o operador saber qual exit code olhar.
        print(f"[ERROR] DSN nao configurado: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        # Outros erros ao obter engine (ex.: DNS, TLS). Diferenciamos de
        # "DSN ausente" porque a acao do operador e' outra (checar rede
        # em vez de configurar secret).
        print(
            f"[ERROR] Falha ao obter engine: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    try:
        init_schema(engine)
    except Exception as e:
        print(
            f"[ERROR] init_schema falhou: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 2

    print("[OK] 11/11 tables created (or already exist)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
