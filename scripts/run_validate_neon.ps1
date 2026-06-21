<#
.SYNOPSIS
    Setup + run scripts/validate_neon.py no data layer Neon (PowerShell).

.DESCRIPTION
    Faz o preparo completo para rodar o smoke test end-to-end do Neon
    em uma unica chamada PowerShell:

      1. Resolve o worktree root a partir de $PSScriptRoot (independente
         do cwd em que o script foi invocado).
      2. Cria .venv com `python -m venv` se ainda nao existir.
      3. Instala requirements.txt se o venv acabou de ser criado OU se
         pandas/psycopg nao estiverem importaveis (defesa contra venv
         parcial criado manualmente).
      4. Carrega .env na sessao atual (NEON_DSN, DCLINIQUE_DSN, etc.).
         Aceita linhas com aspas, com `=` no valor (ex.: DSN com
         `?sslmode=require&...`), e ignora comentarios / linhas vazias.
      5. Seta DCLINIQUE_BACKEND=postgres e roda scripts/validate_neon.py.
      6. Propaga o exit code do validate_neon.py para o caller.

    O script e' idempotente: re-rodar com tudo no lugar so' faz o
    load do .env e a execucao do smoke test (sem recriar venv nem
    reinstalar pacotes).

.PARAMETER DsnPath
    Caminho (relativo ao worktree root, ou absoluto) para o arquivo
    com as env vars. Default: ".env".

.PARAMETER VenvDir
    Diretorio (relativo ao worktree root, ou absoluto) do venv.
    Default: ".venv".

.PARAMETER SkipInstall
    Se setado, pula o passo de pip install mesmo se o venv estiver
    incompleto. Util para debug quando o caller ja' instalou via
    outro caminho.

.EXAMPLE
    # Uso tipico (do worktree root):
    pwsh scripts/run_validate_neon.ps1

.EXAMPLE
    # Apontando para um .env alternativo (e.g., .env.dev):
    pwsh scripts/run_validate_neon.ps1 -DsnPath .env.dev

.EXAMPLE
    # Sem reinstalar (venv ja' tem tudo):
    pwsh scripts/run_validate_neon.ps1 -SkipInstall

.NOTES
    Exit codes (propagados de scripts/validate_neon.py):
      0  -- todos os checks passaram
      1  -- DSN nao configurado
      2  -- falha de conectividade
      3  -- falha de schema
      4  -- falha de CRUD
      5  -- falha de cleanup

    Logs estruturados escritos em:
        data/test_logs/neon_validate_<UTC-timestamp>.log

    Politica de execucao: se o sistema bloquear o .ps1, rode uma vez:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    ou entao use o Python launcher:
        pwsh -ExecutionPolicy Bypass -File scripts/run_validate_neon.ps1
#>
[CmdletBinding()]
param(
    [string]$DsnPath = ".env",
    [string]$VenvDir = ".venv",
    [switch]$SkipInstall
)

# Stop em erros de PowerShell (arquivos nao encontrados, etc.). Erros
# de comandos nativos (python, pip) sao checados via $LASTEXITCODE.
$ErrorActionPreference = "Stop"

function Write-Step($msg)    { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-StepOk($msg)  { Write-Host "[setup] $msg" -ForegroundColor Green }
function Write-StepWarn($msg){ Write-Host "[setup] $msg" -ForegroundColor Yellow }
function Write-StepErr($msg) { Write-Host "[setup] $msg" -ForegroundColor Red }


# 1. Resolve o worktree root. $PSScriptRoot = diretorio deste .ps1.
#    O worktree root e' o pai de `scripts/`, independente do cwd.
$ScriptDir = $PSScriptRoot
$WorktreeRoot = Split-Path -Parent $ScriptDir

# A partir daqui operamos com paths absolutos a partir do worktree root.
Push-Location $WorktreeRoot
try {
    Write-Step "worktree root: $WorktreeRoot"

    $VenvPath         = if (Test-Path $VenvDir) { (Resolve-Path $VenvDir).Path } else { Join-Path $WorktreeRoot $VenvDir }
    $VenvPython       = Join-Path $VenvPath "Scripts\python.exe"
    $EnvFile          = if (Test-Path $DsnPath) { (Resolve-Path $DsnPath).Path } else { Join-Path $WorktreeRoot $DsnPath }
    $RequirementsFile = Join-Path $WorktreeRoot "requirements.txt"
    $ValidateScript   = Join-Path $WorktreeRoot "scripts\validate_neon.py"

    # 2. Cria venv se faltar
    $VenvJustCreated = $false
    if (-not (Test-Path $VenvPython)) {
        Write-Step "venv nao existe em $VenvPath -- criando via 'python -m venv'..."
        python -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) {
            Write-StepErr "falha ao criar venv (exit=$LASTEXITCODE). Verifique se 'python' esta' no PATH e a versao e' 3.10+."
            exit 1
        }
        $VenvJustCreated = $true
        Write-StepOk "venv criado."
    } else {
        Write-Step "venv ja' existe: $VenvPath"
    }

    # 3. Instala requirements se venv foi criado agora OU se pandas/psycopg
    #    nao estiverem importaveis. Streamlit nao e' checado porque o
    #    validate_neon.py importa streamlit dentro de try/except
    #    (funciona sem streamlit quando NEON_DSN esta' setado).
    #
    #    O bloco usa ErrorActionPreference=SilentlyContinue para que o
    #    ModuleNotFoundError do Python NAO encerre o script (default Stop
    #    no escopo do script) -- so' queremos setar $NeedInstall e seguir.
    $NeedInstall = $VenvJustCreated
    if (-not $NeedInstall) {
        $origEAP = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        try {
            foreach ($pkg in @("pandas", "psycopg")) {
                $null = & $VenvPython -c "import $pkg" 2>&1
                if ($LASTEXITCODE -ne 0) {
                    $NeedInstall = $true
                    break
                }
            }
        } finally {
            $ErrorActionPreference = $origEAP
        }
    }

    if ($NeedInstall -and -not $SkipInstall) {
        if (-not (Test-Path $RequirementsFile)) {
            Write-StepErr "requirements.txt nao encontrado em $RequirementsFile"
            exit 1
        }
        Write-Step "instalando requirements (pode levar 1-2 min na primeira vez)..."
        & $VenvPython -m pip install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-StepErr "pip install falhou (exit=$LASTEXITCODE)"
            exit 1
        }
        Write-StepOk "requirements instalados."
    } elseif ($SkipInstall) {
        Write-Step "SkipInstall setado -- pip install nao sera' executado."
    } else {
        Write-Step "requirements ja' instalados (pandas, psycopg presentes)."
    }

    # 4. Carrega .env na sessao. Equivalente PowerShell do bash
    #    `set -a; source .env; set +a`. Trata:
    #      - Linhas vazias e comentarios (`#...`) -> ignoradas
    #      - `KEY=value` -> env var
    #      - `KEY="value"` -> env var sem aspas
    #      - `KEY='value'` -> env var sem aspas
    #      - Valores com `=` no meio (ex.: DSN com `?sslmode=require&...`)
    #        -> split so' no primeiro `=`
    if (Test-Path $EnvFile) {
        Write-Step "carregando $EnvFile"
        $loaded = 0
        Get-Content $EnvFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -eq "" -or $line.StartsWith("#")) { return }
            $parts = $line -split '=', 2
            if ($parts.Count -ne 2) { return }
            $key = $parts[0].Trim()
            if ($key -eq "") { return }
            $value = $parts[1].Trim()
            # Strip surrounding quotes (single or double)
            if ($value.Length -ge 2) {
                $first = $value[0]
                $last  = $value[$value.Length - 1]
                if (($first -eq '"' -and $last -eq '"') -or
                    ($first -eq "'" -and $last -eq "'")) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
            }
            Set-Item -Path "env:$key" -Value $value
            $loaded++
        }
        Write-Step "  $loaded variaveis carregadas"
    } else {
        Write-StepWarn ".env nao encontrado em $EnvFile -- validate_neon.py vai' sair com exit 1 (DSN nao configurado)."
    }

    # 5. Roda validate_neon.py com DCLINIQUE_BACKEND=postgres forçado.
    if (-not (Test-Path $ValidateScript)) {
        Write-StepErr "scripts/validate_neon.py nao encontrado em $ValidateScript"
        exit 1
    }
    $Env:DCLINIQUE_BACKEND = "postgres"
    # PYTHONPATH precisa apontar para o worktree root porque o validate_neon.py
    # faz `from src.data_layer...` no top-level. Sem isso, sys.path[0] e' o
    # diretorio do script (scripts/), e o import de `src` falha.
    $Env:PYTHONPATH = $WorktreeRoot
    Write-Step "rodando scripts/validate_neon.py..."
    & $VenvPython $ValidateScript
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-StepOk "validate_neon.py exit=0 (PASSED)"
    } else {
        Write-StepErr "validate_neon.py exit=$exitCode"
    }
    exit $exitCode
}
finally {
    Pop-Location
}
