"""scripts/import_service_catalog.py — importa catalogo de servicos no data layer.

Le um CSV (lista ativa OU lista da Dane) com as colunas canonicas
esperadas por ``service_catalog`` e faz UPSERT (insert-or-update)
no data layer ativo (CSV local ou Postgres Neon).

Uso
---
    # Importa lista ativa (default source=lista_ativa)
    python scripts/import_service_catalog.py --csv path/to/lista_ativa.csv

    # Importa lista da Dane (marca source='dane' nas linhas com source vazio)
    python scripts/import_service_catalog.py --csv path/to/dane.csv --source dane

    # So' parse + stats, sem gravar nada no data layer
    python scripts/import_service_catalog.py --csv path/to/lista_ativa.csv --dry-run

Colunas obrigatorias no CSV
---------------------------
``service_code, name, classification, category, default_periodicity_days,
source, created_at`` (ordem livre; ver ``src.service_catalog.types``).

Linhas com ``service_code`` ou ``name`` vazios sao puladas (warning).
Linhas com ``classification`` / ``category`` invalidos caem no default
conservador (``active`` / ``None``) com warning. Ver
``src.service_catalog.parse`` para a lista completa de heuristicas.

Nao-destrutivo no sentido de "apaga dados" — UPSERT atualiza o que
existe e cria o que nao existe. Re-rodar com o mesmo CSV e' idempotente
(mesmo ``service_code`` -> mesmo conteudo).

Exit codes:
  0 — OK (todas as linhas processadas, com ou sem erros por linha)
  1 — argumentos invalidos (--csv faltando, --source invalido)
  2 — erro de I/O (arquivo nao encontrado, sem permissao, encoding invalido)
  3 — CSV sem colunas obrigatorias
  4 — erro no data layer (CSV write / Postgres) — ver logs PT-BR
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.service_catalog.parse import parse_catalog_csv
from src.service_catalog.persist import import_catalog


_VALID_SOURCES = ("lista_ativa", "dane")


def _parse_args() -> argparse.Namespace:
    """CLI args. --csv e' obrigatorio."""
    p = argparse.ArgumentParser(
        prog="import_service_catalog.py",
        description=(
            "Importa CSV de catalogo de servicos com UPSERT (insert-or-update) "
            "no data layer ativo. Idempotente: re-rodar nao duplica."
        ),
    )
    p.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Caminho do CSV de entrada (lista ativa ou lista da Dane).",
    )
    p.add_argument(
        "--source",
        choices=_VALID_SOURCES,
        default="lista_ativa",
        help=(
            "Source aplicado quando a coluna 'source' do CSV vier vazia ou "
            "invalida. Default: lista_ativa. Use 'dane' quando o CSV vier "
            "da lista usada pela Dane nos orcamentos."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas parseia o CSV e mostra estatisticas; nao grava nada.",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()

    # 1. Parse do CSV
    try:
        result = parse_catalog_csv(args.csv, default_source=args.source)
    except FileNotFoundError as exc:
        print(f"[ERROR] Arquivo nao encontrado: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"[ERROR] Sem permissao de leitura: {exc}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print(f"[ERROR] Encoding invalido (esperado UTF-8): {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # CSV sem colunas obrigatorias — vindo do parse.py
        print(f"[ERROR] CSV invalido: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        # Outros (pd.errors.EmptyDataError, ParserError, etc.)
        print(
            f"[ERROR] Falha ao parsear CSV: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    # 2. Stats do parse (sempre imprime, mesmo em dry-run)
    print(
        f">>> Parse: {len(result.entries)} entries validas, "
        f"{result.rows_skipped} linhas puladas, "
        f"{result.rows_total} linhas no total.",
        flush=True,
    )

    if args.dry_run:
        print(
            ">>> --dry-run: nenhuma gravacao no data layer foi feita.",
            flush=True,
        )
        return 0

    # 3. UPSERT em batch
    try:
        summary = import_catalog(result.entries)
    except Exception as exc:
        # import_catalog ja' engole erros por linha; isto e' um erro
        # top-level (ex.: data layer indisponivel).
        logging.error("import_catalog falhou no top-level: %s", exc)
        print(
            f"[ERROR] Falha no data layer: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4

    # 4. Resumo
    print(
        f">>> UPSERT: {summary.inserted} inseridos, "
        f"{summary.updated} atualizados, "
        f"{summary.failed} falharam.",
        flush=True,
    )
    if summary.errors:
        print(">>> Erros por linha (primeiros 10):", flush=True)
        for err in summary.errors[:10]:
            print(f"    - {err}", flush=True)
        if len(summary.errors) > 10:
            print(
                f"    ... e mais {len(summary.errors) - 10} erros "
                "(veja logs).",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())