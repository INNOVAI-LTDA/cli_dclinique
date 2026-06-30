<#
.SYNOPSIS
    Setup + run all tests for src/core/ via pytest, with linter and smoke
    pre-checks. Idempotent.

.DESCRIPTION
    Faz o preparo completo para rodar a suite de testes do caminho B em uma
    unica chamada PowerShell, na ordem:

      1. Resolve o worktree root a partir de $PSScriptRoot (independente do
         cwd em que o script foi invocado).
      2. Cria .venv com `python -m venv` se ainda nao existir.
      3. Instala requirements.txt + requirements-dev.txt se o venv acabou
         de ser criado OU se pytest/ruff nao estiverem importaveis.
      4. Carrega .env na sessao atual (NEON_DSN etc.). Aceita linhas com
         aspas, com `=` no valor, e ignora comentarios / linhas vazias.
      5. Seta DCLINIQUE_BACKEND=csv (forca dev offline).
      6. Verifica que nenhuma instancia Streamlit esta rodando em 8501/8502.
      7. ruff check src/core tests/        (linter principal; N2, N4)
      8. python -m compileall src/core tests/ (syntax check)
      9. ruff check --select E722,F401,F811 src/core/ (AST scan anti-bare-except; N7)
     10. pytest TestPattern -v --json-report
     11. grep anti-stacktrace no log (N7)
     12. streamlit smoke test em :8501 (so' se pytest passou)

    Cada etapa aborta com exit != 0 se falhar. O objetivo e' falhar cedo
    na etapa mais barata possivel (linter antes de pytest, pytest antes
    de smoke). Veja docs/caminho_b_plano.md §5.1 para detalhes.

    Nota sobre ErrorActionPreference
    --------------------------------
    O script usa $ErrorActionPreference = "Stop" para que erros internos
    do PowerShell (arquivo nao encontrado, etc.) terminem o script.
    Porem, exit codes != 0 de comandos externos (python, pip, ruff,
    pytest) NAO sao erros do PowerShell -- sao apenas o conteudo de
    $LASTEXITCODE. Sob "Stop", PowerShell *promove* esses exit codes a
    terminating errors, o que dispara o catch block antes de podermos
    ler $LASTEXITCODE e chamar Fail-With com a mensagem correta.

    A solucao (espelhada de scripts/run_validate_neon.ps1) e' resetar
    $ErrorActionPreference para "SilentlyContinue" ao redor de cada
    invocacao de comando externo via o helper Invoke-ExternalStep.
    O $LASTEXITCODE continua sendo lido normalmente; apenas a
    promocao automatica para terminating error e' suprimida.

    Outputs:
      - logs/test_core_<timestamp>.log (humano)
      - logs/test_core_<timestamp>.json (machine-parseable, via pytest-json-report)

.PARAMETER TestPattern
    Pattern de teste para pytest. Default: "tests/".
    Exemplos: "tests/test_core_smoke.py", "tests/test_core_frequency.py".

.PARAMETER MaxTracebacks
    Limiar de marcadores "Traceback (most recent call last)" no .log para a
    checagem N7. Default: 3. Em testes, excecoes sao esperadas; acima desse
    limiar indica que codigo de producao esta deixando excecao vazar.

.PARAMETER VenvDir
    Diretorio (relativo ao worktree root, ou absoluto) do venv.
    Default: ".venv". Para reusar o venv do projeto principal, passe
    "-VenvDir ../.venv".

.PARAMETER SkipInstall
    Se setado, pula o passo de pip install mesmo se o venv estiver incompleto.

.PARAMETER Phase
    Rótulo da fase em execução, exibido em ciano no topo da barra de
    progresso. Default: derivado do TestPattern (ex.: "tests/test_core_*.py"
    → "Fase 1 - Tipos v2 + Repositórios read-only"). Passe explicitamente
    para sobrescrever (ex.: -Phase "Fase 2 - Cálculo de frequência").

.EXAMPLE
    # Uso tipico (do worktree root):
    pwsh scripts/run_core_tests.ps1

.EXAMPLE
    # Rodando so' os smoke tests:
    pwsh scripts/run_core_tests.ps1 -TestPattern "tests/test_core_smoke.py"

.EXAMPLE
    # Reusando o venv do projeto principal (evita reinstalar ~50 pacotes):
    pwsh scripts/run_core_tests.ps1 -VenvDir ../.venv

.EXAMPLE
    # Forçando o rótulo da fase (sobrescreve a auto-detecção):
    pwsh scripts/run_core_tests.ps1 -Phase "Fase 2 - Cálculo de frequência"
#>
[CmdletBinding()]
param(
    [string]$TestPattern = "tests/",
    [int]$MaxTracebacks = 3,
    [string]$VenvDir = ".venv",
    [switch]$SkipInstall,
    [string]$Phase = ""
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Step 1: resolve worktree root from $PSScriptRoot (independent of caller cwd)
# ---------------------------------------------------------------------------
$WorktreeRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $WorktreeRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logDir = Join-Path $WorktreeRoot "logs"
$logFile = Join-Path $logDir "test_core_$timestamp.log"
$jsonFile = Join-Path $logDir "test_core_$timestamp.json"
$venvPython = if ($IsWindows -or $env:OS -eq "Windows_NT") {
    Join-Path $VenvDir "Scripts/python.exe"
} else {
    Join-Path $VenvDir "bin/python"
}

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$script:exitCode = 0

# ---------------------------------------------------------------------------
# Auto-derive phase label from $TestPattern when -Phase is not supplied.
# Mapeamento cobre os arquivos de teste que temos / teremos por fase do
# Caminho B (docs/caminho_b_plano.md §3). O usuario pode sempre passar
# -Phase explicitamente para forçar um rotulo custom.
# ---------------------------------------------------------------------------
if (-not $Phase) {
    $Phase = switch -Wildcard ($TestPattern) {
        "*test_core_smoke*"        { "Fase 1 - Tipos v2 + Repositorios read-only (smoke)" }
        "*test_core_types*"        { "Fase 1 - Tipos v2 + Repositorios read-only (types)" }
        "*test_core_repos*"        { "Fase 1 - Tipos v2 + Repositorios read-only (repos)" }
        "*test_core_mapping*"      { "Fase 1 - Tipos v2 + Repositorios read-only (mapping)" }
        "*test_core_frequency*"    { "Fase 2 - Calculo de frequencia" }
        "*test_core_alerts*"       { "Fase 3 - Alertas e deteccao de padroes" }
        "*test_core_reports*"      { "Fase 4 - Relatorios consolidados" }
        "tests/"                   { "Caminho B - suite completa (atual: Fase 1)" }
        default                    { "Fase ? (rotulo nao inferido de '$TestPattern')" }
    }
}

function Write-Log {
    param([string]$Message)
    $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] $Message"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

function Add-Log {
    # Writes a line to the log file ONLY (no terminal echo). Use during
    # progress updates where the terminal is handling its own in-place
    # display via Write-Host "`r..." - the log file gets the timestamped
    # entry, but the terminal does NOT get a duplicate (which would force
    # a newline and break the in-place update). See user feedback
    # 2026-06-23: "[2026-06-23 14:59:45] [...]" timestamp lines were
    # interleaving with the progress bar, producing a cascade.
    param([string]$Message)
    $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] $Message"
    Add-Content -Path $logFile -Value $line
}

function Fail-With {
    param([string]$Message, [int]$Code = 1)
    Write-Log "ABORT: $Message"
    $script:exitCode = $Code
    throw "ABORT"
}

function Invoke-ExternalStep {
    # Wraps an external command so a non-zero exit does NOT terminate the
    # script under $ErrorActionPreference = "Stop". Stdout+stderr are forwarded
    # to Write-Log line-by-line. Returns $LASTEXITCODE so callers can check it.
    #
    # Mirrors the pattern in scripts/run_validate_neon.ps1 (lines 119-138).
    param(
        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter(Mandatory)]
        [string[]]$Args
    )
    $origPref = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $Command @Args 2>&1 | ForEach-Object { Write-Log $_ }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $origPref
    }
}

function Test-PythonImport {
    # Check if one or more modules are importable in the venv's python.
    # Returns $true if ALL modules import cleanly, $false otherwise.
    # Does NOT terminate the script on a missing module (uses SilentlyContinue).
    param(
        [Parameter(Mandatory)]
        [string]$PythonExe,

        [Parameter(Mandatory)]
        [string[]]$Modules
    )
    $modulesCsv = ($Modules -join ", ")
    $origPref = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $null = & $PythonExe -c "import $modulesCsv" 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $origPref
    }
}

function Invoke-PytestWithProgress {
    # Runs pytest, displays each test as a single updating line in the terminal
    # (with a progress bar) when stdout is a TTY. When stdout is redirected
    # (e.g., to a log file or piped), each test appears on its own line in
    # the log. Returns $LASTEXITCODE.
    #
    # Visual style mirrors pytest-sugar without adding the dependency.
    # Single-line format: [============......]  45% tests/test_x.py::test_y PASSED
    # Colors: Green=PASSED, Red=FAILED/ERROR, Yellow=SKIPPED.
    #
    # Auto-detects TTY via [Console]::IsOutputRedirected. No flag needed.
    #
    # IMPORTANT -- cascade bug fix (2026-06-23):
    #   Earlier versions emitted "`r$displayLine" without padding, so a SHORTER
    #   subsequent line would leave leftover characters from the longer
    #   previous line on the right side, producing a cascade effect (each test
    #   appearing to wrap to a new line). Fix: pad/truncate the display line
    #   to a fixed width ($maxDisplayWidth = Min(80, $termWidth-1)) so each
    #   write fully overwrites the previous line, regardless of length.
    param(
        [Parameter(Mandatory)]
        [string]$PythonExe,

        [Parameter(Mandatory)]
        [string[]]$Args,

        [Parameter(Mandatory=$false)]
        [string]$PhaseLabel = ""
    )

    $useProgress = -not [Console]::IsOutputRedirected
    $origPref = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $barWidth = 20
    # Default width if Console.WindowWidth throws (e.g., captured stdout with
    # no real console attached). See logs/isolate_foreach.ps1 Test 5.
    $termWidth = 120

    try {
        if ($useProgress) {
            # WindowWidth can throw "Identificador inválido" on hosts without a
            # real console. Probe once before the loop so the body stays fast.
            try { $termWidth = [Console]::WindowWidth } catch { $termWidth = 120 }
            # Cascade-bug fix: cap the display line at a fixed width so each
            # CR + write fully overwrites the previous line. Min(80, width-1)
            # keeps it well within typical terminal widths to avoid auto-wrap.
            $maxDisplayWidth = [Math]::Min(80, $termWidth - 1)
            # Try to hide the cursor for cleaner in-place updates. Some hosts
            # (e.g., Windows PowerShell 5.1 with redirected stdout) don't
            # support this; fall back silently.
            try {
                [Console]::CursorVisible = $false
            } catch {
                # Cursor visibility not controllable -- proceed without.
            }
            # Phase banner: a single line above the progress bar so the user
            # can tell which phase is running (the user reported confusion:
            # "não consegui identificar qual fase correspondia").
            if ($PhaseLabel) {
                Write-Host $PhaseLabel -ForegroundColor Cyan
            }
            try {
                & $PythonExe @Args 2>&1 | ForEach-Object {
                    $line = "$_"
                    # Strip ANSI escape codes (ESC + [ + digits/semicolons + letter).
                    # Use `-replace` with `e[ (single-quoted) so PowerShell does
                    # NOT pre-process the backtick escape -- the regex engine
                    # must see a literal ESC byte. See logs/isolate_foreach.ps1
                    # Test 2 vs Test 3 for the difference.
                    $line = $line -replace "`e\[[0-9;]*[a-zA-Z]", ""
                    $line = $line.TrimEnd("`r")
                    # Match pytest's "path::test_name STATUS [ NN%]" pattern.
                    if ($line -match '^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)\s+\[\s*(\d+)%\]') {
                        $testName = $matches[1]
                        $status = $matches[2]
                        $pct = [int]$matches[3]
                        $filled = [Math]::Floor($pct * $barWidth / 100)
                        $bar = "[" + ("=" * $filled) + (" " * ($barWidth - $filled)) + "]"
                        $color = switch ($status) {
                            "PASSED"  { "Green" }
                            "FAILED"  { "Red" }
                            "ERROR"   { "Red" }
                            "SKIPPED" { "Yellow" }
                            default   { "Gray" }
                        }
                        # Truncate test name to fit in $maxDisplayWidth minus the
                        # fixed prefix ("[==.............] 100% " = 30 chars) and
                        # status suffix (max 8 chars). Leaves ~42 chars for name.
                        $overhead = 30 + 8
                        $maxName = [Math]::Max(15, $maxDisplayWidth - $overhead)
                        if ($testName.Length -gt $maxName) {
                            $testName = "..." + $testName.Substring($testName.Length - $maxName + 3)
                        }
                        $displayLine = "$bar $($pct.ToString().PadLeft(3))% $testName $status"
                        # Pad / truncate to EXACTLY $maxDisplayWidth chars so each
                        # subsequent CR+write fully overwrites the previous line.
                        if ($displayLine.Length -gt $maxDisplayWidth) {
                            $paddedLine = $displayLine.Substring(0, $maxDisplayWidth)
                        } else {
                            $paddedLine = $displayLine.PadRight($maxDisplayWidth)
                        }
                        # `r (backtick-r) is carriage return -- cursor back to start
                        # of line WITHOUT advancing; subsequent write overwrites.
                        # Add-Log (not Write-Log) writes the line to the log file
                        # only -- Write-Log would echo to the terminal too, forcing
                        # a newline that breaks the in-place update.
                        Write-Host "`r$paddedLine" -NoNewline -ForegroundColor $color
                        Add-Log $displayLine
                    } else {
                        # Header, summary, warnings, deprecation: emit on a new line.
                        Write-Host "`n$line"
                        Write-Log $line
                    }
                }
            } finally {
                try {
                    [Console]::CursorVisible = $true
                } catch {
                    # Cursor visibility not controllable -- proceed without.
                }
                Write-Host ""  # final newline so the next prompt isn't on the progress line
            }
        } else {
            # Stdout redirected: each line gets its own line in the terminal AND log.
            # Write-Log already echoes to terminal with a timestamp + writes to the
            # log file; do NOT also Write-Host here, or the terminal shows the line
            # twice (once plain, once with timestamp prefix).
            if ($PhaseLabel) {
                Write-Log $PhaseLabel
            }
            & $PythonExe @Args 2>&1 | ForEach-Object {
                $line = "$_"
                Write-Log $line
            }
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $origPref
    }
}

try {
    # -------------------------------------------------------------------------
    # Normalize $TestPattern so users can pass either form:
    #   - bare stem:      "test_core_frequency"
    #   - relative file:  "tests/test_core_frequency.py"
    #   - relative glob:  "tests/test_core_*.py"
    #   - nodeid:         "tests/test_core_frequency.py::test_attendance_rate_normal_case"
    # Without this, pytest interprets the bare stem as a nodeid and reports
    # "collected 0 items" with exit 4 -- confusing for the user. The Phase 2
    # hit this: user (per AI suggestion) ran with "test_core_frequency" and
    # pytest found nothing. See experience_log entry 2026-06-23-153547.
    # -------------------------------------------------------------------------
    $normalizedPattern = $TestPattern
    if ($normalizedPattern -notmatch '[\\/]' -and $normalizedPattern -notmatch '::') {
        # No path separator and no nodeid qualifier -> prepend "tests/"
        $normalizedPattern = "tests/$normalizedPattern"
    }
    if (
        $normalizedPattern -notmatch '\.py$' -and
        $normalizedPattern -notmatch '::' -and
        $normalizedPattern -notmatch '\*' -and
        -not $normalizedPattern.EndsWith('/') -and
        -not $normalizedPattern.EndsWith('\')
    ) {
        # No .py extension, not a glob, not a nodeid, not a directory marker
        # -> append ".py"
        $normalizedPattern = "$normalizedPattern.py"
    }
    $TestPattern = $normalizedPattern

    Write-Log "run_core_tests.ps1 - start"
    Write-Log "worktree: $WorktreeRoot"
    Write-Log "test pattern: $TestPattern"
    Write-Log "max tracebacks threshold: $MaxTracebacks"
    Write-Log "venv: $VenvDir"

    # -------------------------------------------------------------------------
    # Step 2: create venv if missing
    # -------------------------------------------------------------------------
    if (-not (Test-Path $VenvDir)) {
        Write-Log "Creating venv: $VenvDir"
        python -m venv $VenvDir
    } else {
        Write-Log "venv exists: $VenvDir"
    }

    # -------------------------------------------------------------------------
    # Step 3: install requirements (idempotent)
    # -------------------------------------------------------------------------
    if (-not $SkipInstall) {
        $needsInstall = $false
        if (-not (Test-Path $venvPython)) {
            $needsInstall = $true
            Write-Log "  reason: venv python.exe missing"
        } else {
            # Check that the dev deps are importable. Missing any of them
            # (e.g., on a reused main-project venv) triggers a full pip install.
            $devOk = Test-PythonImport -PythonExe $venvPython -Modules @("pytest", "ruff")
            if (-not $devOk) {
                $needsInstall = $true
                Write-Log "  reason: pytest or ruff not importable"
            }
        }
        if ($needsInstall) {
            Write-Log "Installing requirements.txt + requirements-dev.txt"
            $pipExit = Invoke-ExternalStep -Command $venvPython -Args @(
                "-m", "pip", "install", "--quiet",
                "-r", "requirements.txt",
                "-r", "requirements-dev.txt"
            )
            if ($pipExit -ne 0) {
                Fail-With "pip install falhou (exit $pipExit)"
            }
        } else {
            Write-Log "venv OK (pytest, ruff importable)"
        }
    } else {
        Write-Log "Skipping pip install (SkipInstall set)"
    }

    # -------------------------------------------------------------------------
    # Step 4: load .env if exists
    # -------------------------------------------------------------------------
    if (Test-Path ".env") {
        Write-Log "Loading .env"
        Get-Content ".env" | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
                Write-Log "  set $name=<redacted>"
            }
        }
    } else {
        Write-Log "no .env file (using defaults)"
    }

    # -------------------------------------------------------------------------
    # Step 5: force CSV backend
    # -------------------------------------------------------------------------
    $env:DCLINIQUE_BACKEND = "csv"
    Write-Log "backend: csv"

    # -------------------------------------------------------------------------
    # Step 6: verify no stale Streamlit
    # -------------------------------------------------------------------------
    $portsInUse = @()
    foreach ($port in @(8501, 8502)) {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $portsInUse += $port
        }
    }
    if ($portsInUse.Count -gt 0) {
        Fail-With "Streamlit ja' rodando em porta(s) $($portsInUse -join ', '). Mate o processo antes de rodar."
    }
    Write-Log "no stale Streamlit on :8501/:8502"

    # -------------------------------------------------------------------------
    # Step 7: ruff check (linter principal; N2, N4)
    # -------------------------------------------------------------------------
    # Escopo: src/core/ + tests/test_core_*.py (novos arquivos do path B).
    # Os testes v1 pre-existentes (test_pdf_*, test_ficha_*, etc.) NAO estao
    # no escopo deste linter -- foram escritos antes do N2/N4 entrarem em
    # vigor e tem seu proprio regime de qualidade (smoke manual + AppTest).
    Write-Log "Step 7/12: ruff check src/core tests/test_core_*.py"
    $ruffExit = Invoke-ExternalStep -Command $venvPython -Args @(
        "-m", "ruff", "check", "src/core", "tests/test_core_*.py"
    )
    if ($ruffExit -ne 0) {
        Fail-With "ruff check falhou (exit $ruffExit). Corrija erros de lint antes de continuar."
    }
    Write-Log "ruff check passed"

    # -------------------------------------------------------------------------
    # Step 8: python -m compileall (syntax check)
    # -------------------------------------------------------------------------
    # Escopo: src/core/. Os tests/test_core_*.py sao checados via import
    # no step 10 (pytest), entao compileall duplicaria o trabalho.
    Write-Log "Step 8/12: python -m compileall src/core/"
    $compileExit = Invoke-ExternalStep -Command $venvPython -Args @(
        "-m", "compileall", "-q", "src/core/"
    )
    if ($compileExit -ne 0) {
        Fail-With "compileall falhou (exit $compileExit). Erro de sintaxe."
    }
    Write-Log "compileall passed"

    # -------------------------------------------------------------------------
    # Step 9: ruff AST scan (anti-bare-except, anti-duplicate-imports; N7)
    # -------------------------------------------------------------------------
    Write-Log "Step 9/12: ruff check --select E722,F401,F811 src/core/"
    $astScanExit = Invoke-ExternalStep -Command $venvPython -Args @(
        "-m", "ruff", "check", "--select", "E722,F401,F811", "src/core/"
    )
    if ($astScanExit -ne 0) {
        Fail-With "ruff AST scan falhou (exit $astScanExit). Bare except ou import duplicado."
    }
    Write-Log "ruff AST scan passed"

    # -------------------------------------------------------------------------
    # Step 10: pytest with json-report (single-line progress in TTY, line-by-line
    # if stdout is redirected). --tb=line para saida compacta de erros (uma linha
    # por falha, em vez de traceback multi-linha).
    # -------------------------------------------------------------------------
    Write-Log "Step 10/12: pytest $TestPattern -v --tb=line --json-report"
    Write-Log "Phase label: $Phase"
    $pytestExit = Invoke-PytestWithProgress -PythonExe $venvPython -Args @(
        "-m", "pytest", $TestPattern, "-v", "--tb=line",
        "--json-report", "--json-report-file=$jsonFile"
    ) -PhaseLabel $Phase
    if ($pytestExit -ne 0) {
        Write-Log "WARN: pytest reported failures (exit $pytestExit). Continuando para gerar JSON."
        $script:exitCode = 1
    } else {
        Write-Log "pytest passed"
    }

    # -------------------------------------------------------------------------
    # Step 11: anti-stacktrace grep (N7)
    # -------------------------------------------------------------------------
    Write-Log "Step 11/12: anti-stacktrace grep"
    $tracebackCount = 0
    if (Test-Path $logFile) {
        $tracebackCount = (Select-String -Path $logFile -Pattern "Traceback \(most recent call last\)" -ErrorAction SilentlyContinue).Count
    }
    Write-Log "Found $tracebackCount traceback markers in log (threshold: $MaxTracebacks)"
    if ($tracebackCount -gt $MaxTracebacks) {
        Write-Log "N7 VIOLATION: $tracebackCount tracebacks > threshold $MaxTracebacks"
        $script:exitCode = 1
    }

    # -------------------------------------------------------------------------
    # Step 12: streamlit smoke test (only if pytest passed)
    # -------------------------------------------------------------------------
    if ($pytestExit -eq 0) {
        Write-Log "Step 12/12: streamlit smoke test on :8501"
        $streamlitJob = Start-Job -ScriptBlock {
            Set-Location $using:WorktreeRoot
            & $using:venvPython -m streamlit run app.py --server.headless true --server.port 8501 --server.runOnSave false 2>&1
        } -Name "streamlit-smoke"
        Start-Sleep -Seconds 10
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8501/_stcore/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            Write-Log "smoke: streamlit on :8501 - status $($response.StatusCode)"
        } catch {
            Write-Log "smoke: streamlit health endpoint nao respondeu (pode ser normal em algumas versoes)"
            Write-Log "  (raw error: $($_.Exception.Message))"
        }
        Stop-Job -Name "streamlit-smoke" -ErrorAction SilentlyContinue
        Remove-Job -Name "streamlit-smoke" -Force -ErrorAction SilentlyContinue
    } else {
        Write-Log "Step 12/12: smoke test SKIPPED (pytest had failures)"
    }

    Write-Log "run_core_tests.ps1 - done (exit $script:exitCode)"
    Write-Log "LOG: $logFile"
    Write-Log "JSON: $jsonFile"
} catch {
    if ($_.Exception.Message -ne "ABORT") {
        Write-Log "FATAL: $_"
        $script:exitCode = 1
    }
}

exit $script:exitCode