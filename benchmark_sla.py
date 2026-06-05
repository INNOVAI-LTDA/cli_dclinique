"""
SLA benchmark for the MAP Streamlit app.

Three measurement layers:
  L1 - Python render() cost per page (deterministic, isolates logic)
  L2 - Streamlit server cold start (imports + load)
  L3 - HTTP roundtrip for /?nav=<page> (closest to user-perceived load time
       given a headless browser is not available)

Navigation graph is taken from src/navigation.PAGES plus the
Pacientes -> Ficha do Paciente in-app transition wired in
src/pages/pacientes.py (open_patient).
"""
from __future__ import annotations

import io
import json
import os
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import requests

WORKTREE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKTREE))
# Walk up to find the main checkout that owns the venv.
MAIN_ROOT = WORKTREE
for parent in WORKTREE.parents:
    if (parent / ".venv" / "Scripts" / "streamlit.exe").exists():
        MAIN_ROOT = parent
        break
# `ROOT` is the directory the Streamlit server should run from.
# When a venv is present in the worktree itself we use it; otherwise we
# point at the main checkout but still run the worktree's copy of app.py.
VENV_DIR = WORKTREE / ".venv"
if not (VENV_DIR / "Scripts" / "streamlit.exe").exists():
    VENV_DIR = MAIN_ROOT / ".venv"
ROOT = WORKTREE
STREAMLIT_EXE = VENV_DIR / "Scripts" / "streamlit.exe"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe"
SIDEBAR_PAGES = [
    "Visão Geral",
    "Mapa de Decisão",
    "Pacientes",
    "Alertas",
    "Atualização de Dados",
    "Qualidade dos Dados",
]
INTERNAL_PAGE = "Ficha do Paciente"
ALL_PAGES = SIDEBAR_PAGES + [INTERNAL_PAGE]

# Transitions we care about, in the order they happen during a user session
TRANSITIONS: list[tuple[str, str, str]] = [
    ("cold", "Visão Geral", "Initial load (Visão Geral)"),
    ("Visão Geral", "Mapa de Decisão", "Sidebar"),
    ("Mapa de Decisão", "Pacientes", "Sidebar"),
    ("Pacientes", "Ficha do Paciente", "In-app (open_patient)"),
    ("Ficha do Paciente", "Alertas", "Sidebar"),
    ("Alertas", "Atualização de Dados", "Sidebar"),
    ("Atualização de Dados", "Qualidade dos Dados", "Sidebar"),
    ("Qualidade dos Dados", "Visão Geral", "Sidebar"),
]


# ---------------------------------------------------------------------------
# Stubs for streamlit so we can time render() in isolation
# ---------------------------------------------------------------------------


class _StubSession(dict):
    def __getattr__(self, key):
        v = self.get(key)
        # also store on the dict to make setattr work
        return v

    def __setattr__(self, key, value):
        self[key] = value


class _Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Sidebar:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name):
        return lambda *a, **kw: _Ctx()
    def __call__(self, *a, **kw): return self


class _CacheDecorator:
    def __call__(self, fn=None, *a, **kw):
        if fn is None:
            return lambda f: f
        return fn


class _StreamlitStub:
    """Permissive Streamlit stub that records nothing but lets pages run."""

    def __init__(self):
        self.session_state = _StubSession()
        self.session_state["page"] = "Visão Geral"
        self.session_state["selected_patient_id"] = None
        self.session_state["last_update_at"] = None
        self.session_state.setdefault("patients_table_state", {})
        self.session_state.setdefault("alerts_table_state", {})
        self.query_params = {}
        self.cache_data = _CacheDecorator()

    def __getattr__(self, name):
        return lambda *a, **kw: None


@contextmanager
def stub_streamlit():
    import streamlit as real_streamlit
    fake = _StreamlitStub()

    # Specialised callables returning useful objects
    def _spinner(*a, **kw): return _Ctx()
    def _columns(spec, **kw):
        n = len(spec) if hasattr(spec, "__len__") and not isinstance(spec, int) else int(spec)
        return [_Ctx() for _ in range(n)]
    def _tabs(spec, **kw): return [_Ctx() for _ in spec]
    def _sidebar(): return _Sidebar()
    def _rerun(*a, **kw): pass
    def _stop(*a, **kw): raise SystemExit(0)

    fake.spinner = _spinner
    fake.columns = _columns
    fake.tabs = _tabs
    fake.sidebar = _sidebar
    fake.rerun = _rerun
    fake.stop = _stop
    fake.exception = lambda *a, **kw: None

    sys.modules["streamlit"] = fake
    try:
        yield fake, fake.session_state
    finally:
        sys.modules["streamlit"] = real_streamlit


def time_render(page: str, session, data) -> float:
    """Time the render() function of a page module with the stubbed streamlit."""
    from src.pages import (
        alertas,
        atualizacao_dados,
        ficha_paciente,
        mapa_decisao,
        pacientes,
        qualidade_dados,
        visao_geral,
    )

    routes = {
        "Visão Geral": visao_geral.render,
        "Mapa de Decisão": mapa_decisao.render,
        "Pacientes": pacientes.render,
        "Ficha do Paciente": ficha_paciente.render,
        "Alertas": alertas.render,
        "Atualização de Dados": atualizacao_dados.render,
        "Qualidade dos Dados": qualidade_dados.render,
    }

    fn = routes[page]
    session["page"] = page
    if page == "Ficha do Paciente" and not session.get("selected_patient_id"):
        session["selected_patient_id"] = "pat_001"

    sink_out, sink_err = io.StringIO(), io.StringIO()
    t0 = time.perf_counter()
    with redirect_stdout(sink_out), redirect_stderr(sink_err):
        try:
            fn(data)
        except SystemExit:
            pass
        except Exception as exc:  # pragma: no cover - we still want the timing
            sys.stderr.write(f"render({page}) raised: {exc!r}\n")
    return (time.perf_counter() - t0) * 1000.0


def time_main(page: str, session, data) -> float:
    """Time the full app.main() (sidebar + render) – the rerun cost on navigation."""
    import app as app_module

    session["page"] = page
    if page == "Ficha do Paciente" and not session.get("selected_patient_id"):
        session["selected_patient_id"] = "pat_001"

    sink_out, sink_err = io.StringIO(), io.StringIO()
    t0 = time.perf_counter()
    with redirect_stdout(sink_out), redirect_stderr(sink_err):
        try:
            app_module.main()
        except SystemExit:
            pass
        except Exception as exc:
            sys.stderr.write(f"main({page}) raised: {exc!r}\n")
    return (time.perf_counter() - t0) * 1000.0


def benchmark_render_layer(runs: int = 5) -> dict:
    from src.mock_data import load_mock_data
    data = load_mock_data()
    results: dict = {}
    with stub_streamlit() as (_, session):
        for page in ALL_PAGES:
            samples = [time_render(page, session, data) for _ in range(runs)]
            results[page] = {
                "samples_ms": [round(s, 1) for s in samples],
                "mean_ms": round(statistics.mean(samples), 1),
                "median_ms": round(statistics.median(samples), 1),
                "min_ms": round(min(samples), 1),
                "max_ms": round(max(samples), 1),
            }
    return results


def benchmark_data_load_layer(runs: int = 5) -> dict:
    """Time the load_mock_data() call – it is on the critical path of every rerun."""
    from src.mock_data import load_mock_data
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        load_mock_data()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "samples_ms": [round(s, 1) for s in samples],
        "mean_ms": round(statistics.mean(samples), 1),
        "median_ms": round(statistics.median(samples), 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
    }


def benchmark_module_import_layer() -> dict:
    """Time `import app` and `import src.pages.<page>` from a fresh interpreter.

    Captures the cost that lazy imports save on cold start: a fresh
    Python is spawned for each import to bypass the module cache, and
    the wall-clock time of the import is measured.
    """
    targets = {
        "app": "import app",
        "src.pages.mapa_decisao": "import src.pages.mapa_decisao",
        "src.pages.ficha_paciente": "import src.pages.ficha_paciente",
        "src.pages.pacientes": "import src.pages.pacientes",
        "src.pages.qualidade_dados": "import src.pages.qualidade_dados",
        "src.charts.weight_chart": "import src.charts.weight_chart",
    }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["STREAMLIT_RUNTIME_DISABLED"] = "1"
    results: dict = {}
    for label, snippet in targets.items():
        # 3 samples to be robust against disk cache effects
        samples = []
        for _ in range(3):
            t0 = time.perf_counter()
            subprocess.run(
                [str(PYTHON_EXE), "-X", "utf8", "-c", snippet],
                env=env, capture_output=True, check=False,
            )
            samples.append((time.perf_counter() - t0) * 1000.0)
        results[label] = {
            "samples_ms": [round(s, 1) for s in samples],
            "median_ms": round(statistics.median(samples), 1),
            "min_ms": round(min(samples), 1),
        }
    return results


# ---------------------------------------------------------------------------
# Layer 2 - Streamlit server cold start
# ---------------------------------------------------------------------------


def _spawn_server(port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHERUSAGESTATS"] = "false"
    log_fh = open(log_path, "w", encoding="utf-8")
    return subprocess.Popen(
        [
            str(STREAMLIT_EXE),
            "run",
            "app.py",
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--server.runOnSave", "false",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    ), log_fh


def _wait_ready(port: int, max_wait: int = 90) -> None:
    url_health = f"http://127.0.0.1:{port}/_stcore/health"
    url_root = f"http://127.0.0.1:{port}/"
    deadline = time.perf_counter() + max_wait
    last_err: str = ""
    while time.perf_counter() < deadline:
        # Try the dedicated health endpoint first
        try:
            r = requests.get(url_health, timeout=1.0)
            if r.status_code == 200 and r.text.strip() == "ok":
                return
            last_err = f"health status={r.status_code} body={r.text[:80]!r}"
        except requests.RequestException as e:
            last_err = f"health exc={e!r}"
        # Fallback: any 200 from the root means the server is serving
        try:
            r2 = requests.get(url_root, timeout=1.0)
            if r2.status_code == 200 and b"streamlit" in r2.content.lower():
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Streamlit did not become ready on port {port} within {max_wait}s (last: {last_err})")


def _kill(proc: subprocess.Popen, log_fh) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_fh.close()


def _force_release_port(port: int) -> None:
    """Kill any process listening on `port` so the next start is genuinely cold."""
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            return
        pids: set[str] = set()
        marker = f":{port} "
        for line in out.splitlines():
            if "LISTENING" in line and marker in line:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
            except Exception:
                pass
    else:
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
        except Exception:
            pass
    time.sleep(1.0)


def measure_cold_start(port: int, max_wait: int = 90) -> float:
    _force_release_port(port)
    proc, log_fh = _spawn_server(port, ROOT / "benchmark_streamlit_cold.log")
    t0 = time.perf_counter()
    try:
        _wait_ready(port, max_wait)
        return (time.perf_counter() - t0) * 1000.0
    finally:
        _kill(proc, log_fh)
        _force_release_port(port)


# ---------------------------------------------------------------------------
# Layer 3 - HTTP page load via ?nav=<page>
# ---------------------------------------------------------------------------


def measure_http_layer(port: int, runs: int = 3) -> dict:
    _force_release_port(port)
    proc, log_fh = _spawn_server(port, ROOT / "benchmark_streamlit_http.log")
    try:
        _wait_ready(port)
        base = f"http://127.0.0.1:{port}/"
        results: dict = {}
        for page in SIDEBAR_PAGES:
            samples = []
            last_body = b""
            for _ in range(runs):
                t0 = time.perf_counter()
                r = requests.get(base, params={"nav": page}, timeout=15, allow_redirects=True)
                last_body = r.content
                samples.append((time.perf_counter() - t0) * 1000.0)
            results[page] = {
                "samples_ms": [round(s, 1) for s in samples],
                "mean_ms": round(statistics.mean(samples), 1),
                "median_ms": round(statistics.median(samples), 1),
                "min_ms": round(min(samples), 1),
                "max_ms": round(max(samples), 1),
                "bytes": len(last_body),
                "status": r.status_code,
            }
        return results
    finally:
        _kill(proc, log_fh)
        _force_release_port(port)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def classify_sla(ms: float) -> str:
    """Common UX thresholds: <100ms instant, <1s fast, <3s acceptable, >3s slow."""
    if ms < 100:
        return "🟢 instantâneo"
    if ms < 1000:
        return "🟢 rápido"
    if ms < 3000:
        return "🟡 aceitável"
    if ms < 5000:
        return "🟠 lento"
    return "🔴 crítico"


def run() -> dict:
    print("== Layer 0: cold module import time ==", flush=True)
    import_layer = benchmark_module_import_layer()
    for label, r in import_layer.items():
        print(f"  {label:<32} median={r['median_ms']:>7.1f}ms  min={r['min_ms']:>7.1f}ms", flush=True)

    print("\n== Layer 1: per-page render() timing ==", flush=True)
    render_layer = benchmark_render_layer(runs=5)
    for page, r in render_layer.items():
        print(f"  {page:<26} mean={r['mean_ms']:>7.1f}ms  median={r['median_ms']:>7.1f}ms", flush=True)

    print("\n== Layer 1b: load_mock_data() (uncached) ==", flush=True)
    data_layer = benchmark_data_load_layer(runs=5)
    print(f"  load_mock_data              mean={data_layer['mean_ms']:>7.1f}ms  median={data_layer['median_ms']:>7.1f}ms", flush=True)

    print("\n== Layer 2: Streamlit cold start ==", flush=True)
    cold_ms = measure_cold_start(port=8765, max_wait=120)
    print(f"  server ready in {cold_ms:.0f}ms", flush=True)

    print("\n== Layer 3: HTTP GET /?nav=<page> ==", flush=True)
    http_layer = measure_http_layer(port=8766, runs=3)
    for page, r in http_layer.items():
        print(f"  {page:<26} mean={r['mean_ms']:>7.1f}ms  median={r['median_ms']:>7.1f}ms  bytes={r['bytes']}", flush=True)

    return {
        "imports": import_layer,
        "render": render_layer,
        "data_load": data_layer,
        "cold_start_ms": round(cold_ms, 1),
        "http": http_layer,
    }


if __name__ == "__main__":
    out = run()
    Path(ROOT / "benchmark_sla_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nSaved benchmark_sla_results.json")
