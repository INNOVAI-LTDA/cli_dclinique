"""Test T15: docs atualizadas para o data layer Postgres (Neon).

T15 e' a unica task com excecao da regra "1 arquivo" — pode modificar
4 docs. Esta task fecha o release inicial ao garantir que a documentacao
publica (DEPLOY.md, README.md) e os arquivos de config (secrets.toml.example)
+ o SLA_REPORT.md refletem a nova arquitetura Postgres-first.

Verificacoes estruturais (sem runtime):

  DEPLOY.md:
    - §2 (LGPD gate) tem item 5 sobre Neon
    - §4 (Secrets) menciona bloco [postgres]
    - §7 (Rollback) menciona Neon (nao CSV)
    - §8 (Limites) tem nota sobre Neon cold start
    - §9 (Arquivos) lista postgres_backend.py / connection.py / schema.py
    - §11, §12, §13 existem com o conteudo esperado

  .streamlit/secrets.toml.example:
    - tem bloco [postgres] com dsn placeholder
    - mantem secoes comentadas (supabase, integrations)

  SLA_REPORT.md:
    - tem §6 sobre cold start do Neon
    - tem §9 sobre migracao para Postgres

  README.md:
    - Stack inclui psycopg
    - Estrutura menciona postgres_backend.py
    - NAO contem a frase antiga "fonte de verdade em runtime" (referindo-se
      a data/csv/) — foi removida no T15
    - Backend em runtime documenta DCLINIQUE_BACKEND
"""
import re
import sys
from pathlib import Path

TID = "T15"
TITLE = "Atualizar DEPLOY.md + secrets.toml.example + SLA_REPORT.md + README.md (Postgres-first)"

DEPLOY = Path("DEPLOY.md")
SECRETS_EXAMPLE = Path(".streamlit/secrets.toml.example")
SLA_REPORT = Path("SLA_REPORT.md")
README = Path("README.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_body(text: str, section_number: int) -> str:
    """Retorna o corpo (ate' o proximo `## N.`) da secao `## <section_number>.`."""
    pattern = re.compile(
        rf"^##\s+{section_number}\.\s+.*?(?=^##\s+\d+\.\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(0) if m else ""


def _has_section(text: str, section_number: int, title_substring: str) -> bool:
    """Verifica se existe `## <n>. ... <title_substring> ...`."""
    body = _section_body(text, section_number)
    return bool(body) and title_substring.lower() in body.lower()


def check_deploy() -> list[str]:
    failures = []
    if not DEPLOY.exists():
        return [f"{DEPLOY} nao encontrado"]
    text = _read(DEPLOY)

    sec2 = _section_body(text, 2)
    if "Neon" not in sec2:
        failures.append("DEPLOY.md §2 nao menciona Neon")
    if not re.search(r"^5\.", sec2, re.MULTILINE):
        failures.append("DEPLOY.md §2 nao tem item numerado 5.")

    sec4 = _section_body(text, 4)
    if "[postgres]" not in sec4:
        failures.append("DEPLOY.md §4 nao menciona bloco [postgres]")

    sec7 = _section_body(text, 7)
    if "Neon" not in sec7:
        failures.append("DEPLOY.md §7 nao menciona Neon (rollback)")
    if "dados de data/csv/" in sec7:
        failures.append(
            "DEPLOY.md §7 ainda diz 'dados de data/csv/' "
            "(deveria ser dados do Neon)"
        )

    sec8 = _section_body(text, 8)
    if "neon cold start" not in sec8.lower():
        failures.append("DEPLOY.md §8 nao menciona Neon cold start")

    sec9 = _section_body(text, 9)
    for required in ["postgres_backend.py", "connection.py", "schema.py",
                      "init_neon_schema.py", "make_synthetic_pdf.py"]:
        if required not in sec9:
            failures.append(f"DEPLOY.md §9 nao lista {required}")

    if not _has_section(text, 11, "schema em runtime"):
        failures.append("DEPLOY.md nao tem §11 (schema em runtime)")
    if not _has_section(text, 12, "Como rodar localmente"):
        failures.append("DEPLOY.md nao tem §12 (Como rodar local Neon)")
    if not _has_section(text, 13, "Neon Postgres"):
        failures.append("DEPLOY.md nao tem §13 (Neon Postgres)")

    sec13 = _section_body(text, 13)
    for required in ["Provisionamento", "NEON_DSN", "init_neon_schema.py",
                      "Cold start", "LGPD"]:
        if required not in sec13:
            failures.append(f"DEPLOY.md §13 falta referencia a '{required}'")

    return failures


def check_secrets_example() -> list[str]:
    failures = []
    if not SECRETS_EXAMPLE.exists():
        return [f"{SECRETS_EXAMPLE} nao encontrado"]
    text = _read(SECRETS_EXAMPLE)

    if "[postgres]" not in text:
        failures.append("secrets.toml.example: falta [postgres]")
    if "dsn" not in text or "postgresql://" not in text:
        failures.append("secrets.toml.example: [postgres] sem dsn placeholder")
    if "[supabase]" not in text:
        failures.append("secrets.toml.example: perdeu [supabase] (legado)")
    if "[integrations]" not in text:
        failures.append("secrets.toml.example: perdeu [integrations] (legado)")

    return failures


def check_sla_report() -> list[str]:
    failures = []
    if not SLA_REPORT.exists():
        return [f"{SLA_REPORT} nao encontrado"]
    text = _read(SLA_REPORT)

    sec6 = _section_body(text, 6)
    if "cold start" not in sec6.lower() or "neon" not in sec6.lower():
        failures.append("SLA_REPORT.md §6 nao e' sobre cold start do Neon")
    else:
        if "500" not in sec6:
            failures.append("SLA_REPORT.md §6 nao menciona 500 ms")
        if "auto-suspend" not in sec6 and "auto suspend" not in sec6.lower():
            failures.append("SLA_REPORT.md §6 nao menciona auto-suspend")
        if "mitigacao" not in sec6.lower() and "mitigation" not in sec6.lower():
            failures.append("SLA_REPORT.md §6 nao tem mitigacao")

    sec9 = _section_body(text, 9)
    if "postgres" not in sec9.lower() and "neon" not in sec9.lower():
        failures.append("SLA_REPORT.md §9 nao menciona Postgres/Neon")

    return failures


def check_readme() -> list[str]:
    failures = []
    if not README.exists():
        return [f"{README} nao encontrado"]
    text = _read(README)

    if "psycopg" not in text:
        failures.append("README.md Stack nao inclui psycopg")

    if "postgres_backend" not in text:
        failures.append("README.md Estrutura nao menciona postgres_backend")

    if "DCLINIQUE_BACKEND" not in text:
        failures.append("README.md nao documenta DCLINIQUE_BACKEND")

    if "fonte de verdade em runtime" in text:
        failures.append(
            "README.md ainda diz 'fonte de verdade em runtime' "
            "(CSVs agora sao schema reference)"
        )

    return failures


def main() -> int:
    all_failures: list[str] = []
    for name, fn in [
        ("DEPLOY.md", check_deploy),
        ("secrets.toml.example", check_secrets_example),
        ("SLA_REPORT.md", check_sla_report),
        ("README.md", check_readme),
    ]:
        failures = fn()
        if failures:
            all_failures.extend(f"[{name}] {f}" for f in failures)

    if all_failures:
        print(f"[FAIL] {TID}: {TITLE}")
        for f in all_failures:
            print(f"  - {f}")
        return 1

    print(f"[PASS] {TID}: {TITLE}")
    print(f"  DEPLOY.md:")
    print(f"    - §2 item 5 (Neon sign-off): OK")
    print(f"    - §4 [postgres] secrets: OK")
    print(f"    - §7 rollback Neon: OK")
    print(f"    - §8 Neon cold start: OK")
    print(f"    - §9 arquivos novos: OK (postgres_backend / connection / schema / init_neon / synthetic)")
    print(f"    - §11/§12/§13 secoes: OK")
    print(f"  secrets.toml.example: [postgres] ativo, [supabase]/[integrations] legados OK")
    print(f"  SLA_REPORT.md: §6 Neon cold start + §9 migracao Postgres OK")
    print(f"  README.md: psycopg no Stack, postgres_backend na Estrutura, DCLINIQUE_BACKEND documentado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
