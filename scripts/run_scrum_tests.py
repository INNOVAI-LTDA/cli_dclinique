"""Master test runner para o Scrum board do PRD cleanup (Neon Postgres).

Uso (a partir da raiz do projeto):
    python scripts/run_scrum_tests.py                     # roda todas
    python scripts/run_scrum_tests.py --only T3           # roda só T3
    python scripts/run_scrum_tests.py --from T5           # roda T5 em diante
    python scripts/run_scrum_tests.py --stop-on-fail      # para no primeiro FAIL

Saída:
    - stdout: status por task em tempo real
    - data/test_logs/scrum_<timestamp>.log: log estruturado com timestamp,
      level (INFO/PASS/FAIL/ERROR), task_id e mensagem; tudo que importa
      pra debugar a falha fica nesse arquivo.

Formato do log (cada linha):
    [2026-06-18T14:32:11.123] PASS  T3    Create src/data_layer/schema.py

O log é o único artefato que precisa ser colado de volta pro agente quando
houver falha — grep por `FAIL ` e o que vem em seguida é o diagnóstico.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "test_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# (task_id, title, script_path, scope, expected)
TASKS = [
    ("T1",  "Adicionar psycopg[binary] em requirements.txt",
     "scripts/test_T1.py", "1 file: requirements.txt",
     "linha `psycopg[binary]>=3.2,<4` presente"),
    ("T2",  "Criar src/data_layer/connection.py",
     "scripts/test_T2.py", "1 new file",
     "get_engine() importável, cacheado, lê st.secrets"),
    ("T3",  "Criar src/data_layer/schema.py",
     "scripts/test_T3.py", "1 new file",
     "to_ddl() e init_schema() funcionais, 11 CREATE TABLE"),
    ("T4",  "Criar src/data_layer/postgres_backend.py",
     "scripts/test_T4.py", "1 new file",
     "9 funções públicas implementadas (load_all, append_row, ...)"),
    ("T5",  "Criar scripts/init_neon_schema.py",
     "scripts/test_T5.py", "1 new file",
     "Script roda e chama init_schema() (11 tabelas)"),
    ("T6",  "Criar scripts/make_synthetic_pdf.py",
     "scripts/test_T6.py", "1 new file",
     "Gera PDF PII-clean válido em data/synthetic/orcamento_demo.pdf"),
    ("T7",  "Atualizar src/data_layer/__init__.py",
     "scripts/test_T7.py", "1 file modified",
     "Router Postgres/CSV baseado em DCLINIQUE_BACKEND"),
    ("T8",  "Verificar app.py:get_data()",
     "scripts/test_T8.py", "0 files modified",
     "Import limpo e roteamento para o backend ativo"),
    ("T9",  "Limpar data/csv/*.csv",
     "scripts/test_T9.py", "11 files modified",
     "Headers preservados, 0 linhas em todas as 11 tabelas"),
    ("T10", "Atualizar tests/conftest.py (db_branch fixture)",
     "scripts/test_T10.py", "1 file modified",
     "Fixture db_branch usa Neon API (cria/deleta branch)"),
    ("T11", "Atualizar test_add_patient_unit.py",
     "scripts/test_T11.py", "1 file modified",
     "Assertions de count: 0+1=1 (era 8+1=9)"),
    ("T12", "Atualizar test_pdf_importer.py",
     "scripts/test_T12.py", "1 file modified",
     "Assertions de count: 0+1=1 (era 8+1=9)"),
    ("T13", "Atualizar test_integration.py",
     "scripts/test_T13.py", "1 file modified",
     "pat_001 substituído por paciente criado no setup"),
    ("T14", "Atualizar test_ficha_unit.py",
     "scripts/test_T14.py", "1 file modified",
     "Seed-dependência resolvida com setup próprio"),
    ("T15", "Atualizar DEPLOY.md + secrets.toml.example + SLA_REPORT.md + README.md",
     "scripts/test_T15.py", "4 files modified",
     "Docs PRD-release-ready (Neon §12, sign-off item 5, auto-suspend)"),
]


def log_line(log, level, tid, msg):
    line = f"[{datetime.now().isoformat()}] {level:<5} {tid:<4} {msg}\n"
    log.write(line)
    log.flush()
    print(line.rstrip())


def main():
    parser = argparse.ArgumentParser(description="Run Scrum board tests")
    parser.add_argument("--only", help="Run only this task ID (e.g., T3)")
    parser.add_argument("--from", dest="from_task", help="Start from this task ID")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="Stop on first failure")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"scrum_{timestamp}.log"

    print("=== Scrum Run ===")
    print(f"Log:   {log_path}")
    print(f"Args:  {vars(args)}")
    print()

    failed: list[str] = []
    skipped: list[str] = []
    passed: list[str] = []
    started = bool(args.only) or bool(args.from_task) is False

    with log_path.open("w", encoding="utf-8") as log:
        log_line(log, "INFO", "RUN", f"scrum_run started log={log_path.name}")
        log.write(f"  args: {vars(args)}\n")

        for tid, title, script, scope, expected in TASKS:
            if args.only and tid != args.only:
                skipped.append(tid)
                continue
            if args.from_task and not started:
                if tid == args.from_task:
                    started = True
                else:
                    skipped.append(tid)
                    continue
            if args.from_task is None and args.only is None:
                started = True

            log_line(log, "INFO", tid, f"START  {title}")
            log.write(f"  scope:    {scope}\n")
            log.write(f"  expected: {expected}\n")
            log.write(f"  cmd:      python {script}\n")

            script_path = ROOT / script
            if not script_path.exists():
                log.write(f"  ERROR:    test script nao encontrado: {script}\n")
                log_line(log, "FAIL", tid, f"{title} (script not found)")
                failed.append(tid)
                if args.stop_on_fail:
                    break
                continue

            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True, text=True, cwd=ROOT,
            )

            if result.stdout:
                log.write("  STDOUT:\n")
                for line in result.stdout.splitlines():
                    log.write(f"    {line}\n")
            if result.stderr:
                log.write("  STDERR:\n")
                for line in result.stderr.splitlines():
                    log.write(f"    {line}\n")

            if result.returncode == 0:
                log_line(log, "PASS", tid, title)
                passed.append(tid)
            else:
                log_line(log, "FAIL", tid,
                         f"{title} (exit={result.returncode})")
                failed.append(tid)
                if args.stop_on_fail:
                    log_line(log, "INFO", "RUN", "stopped-on-failure")
                    break

        log_line(log, "INFO", "RUN",
                 f"DONE passed={passed} failed={failed} skipped={skipped}")

    print()
    print("=== Summary ===")
    print(f"Passed: {len(passed)}  "
          f"Failed: {len(failed)}  Skipped: {len(skipped)}")
    if failed:
        print(f"FAIL details: {failed}")
        print(f"Log:          {log_path}")
        sys.exit(1)
    print(f"All passed. Log: {log_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
