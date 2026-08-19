<#
.SYNOPSIS
    Local runner for the vertical-slice demo (docs/DEMO_VERTICAL_SLICE.md).

.DESCRIPTION
    Wraps the documented steps so the demo can be started, reset and verified
    without retyping environment variables.

    Two databases live in one container and must stay separate:

      exercise_app_demo   the running demo; holds the synthetic catalog and
                          whatever the demo account creates
      exercise_app_test   scratch database for pytest, recreated on each run

    Sharing one database breaks the repository integration tests, which insert
    their own catalog lookup rows and assume those tables start empty.

    This script is for local demo work only. It sets APP_ENV=local and targets
    throwaway databases, and the seed it calls refuses anything else. It holds
    no secrets: the birthdate key is a local-only test value generated at run
    time, and FIREBASE_PROJECT_ID is read from your own environment.

.PARAMETER Command
    up      Start PostgreSQL 16, apply migrations, install the synthetic seed.
    api     Run FastAPI on 0.0.0.0:8000 (foreground; Ctrl+C to stop).
    share   Point the app at this machine's current LAN IP for a team demo.
    seed    Re-install the synthetic catalog (idempotent).
    rules   Load the reviewed rule bundle and activate the catalog carrying it,
            so a check-in that reports discomfort no longer fails closed.
            Demo database only: that catalog has no recorded domain review.
            Currently stops at activation - the imported catalog has no
            prescription or goal-tag rows, so no routine could be built from
            it. See docs/DEMO_VERTICAL_SLICE.md section 4.1.
    reset   Delete demo users, then re-install the catalog.
    test    Run the backend and frontend verification suites.
    psql    Open a psql shell on the demo database.
    down    Remove the PostgreSQL container.

.EXAMPLE
    .\scripts\demo-local.ps1 up
    .\scripts\demo-local.ps1 api
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('up', 'api', 'share', 'seed', 'rules', 'reset', 'test', 'psql', 'down')]
    [string]$Command
)

# Native tools here (uv, docker, npm) write progress to stderr. Under Windows
# PowerShell 5.1 a redirected native stderr becomes a NativeCommandError, so
# success is checked with $LASTEXITCODE instead of the error stream.
$ErrorActionPreference = 'Continue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ContainerName = 'helkki-demo-pg'
$HostPort = 55432
$DemoDatabase = 'exercise_app_demo'
$TestDatabase = 'exercise_app_test'
# Only one catalog version can be ACTIVE, and this is the only one in the
# bundle that carries all three training types (CARDIO, MOBILITY, STRENGTH),
# so it is the only one a warmup/main/cooldown routine can be built from.
$RuleCatalogVersion = 'kspo-mvp-v0.2.0'

Set-Location $RepoRoot

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host "==> $Description"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit code $LASTEXITCODE)"
    }
}

function Get-LanIPv4 {
    (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.InterfaceAlias -notmatch 'Loopback|WSL|vEthernet' -and
            $_.IPAddress -notmatch '^169\.'
        } | Select-Object -First 1).IPAddress
}

function Set-DemoEnvironment {
    $env:APP_ENV = 'local'
    $env:DATABASE_URL = "postgresql+psycopg://exercise_app:local_dev_only@localhost:$HostPort/$DemoDatabase"
    $env:TEST_DATABASE_URL = "postgresql+psycopg://exercise_app:local_dev_only@localhost:$HostPort/$TestDatabase"
    $env:CONSENT_POLICY_VERSION = 'demo-consent-v1'
    # pydantic-settings parses tuple fields as JSON, so these must be JSON arrays.
    $env:ONBOARDING_PRIMARY_GOAL_CODES = '["GENERAL_FITNESS"]'
    $env:ONBOARDING_EXPERIENCE_LEVEL_CODES = '["BEGINNER"]'
    # Local/test only. Staging and production use the reviewed KMS-backed cipher.
    $env:BIRTHDATE_ENCRYPTION_KEY_BASE64 = [Convert]::ToBase64String([byte[]]::new(32))
    # Lets the browser build (expo start --web) call the API. Native builds send
    # no Origin header and do not need this. Exact origins only; '*' is rejected.
    # The LAN address is included because Expo may open the page there rather
    # than on loopback, and an unlisted origin is refused by the browser in a
    # way the app can only report as a generic network failure.
    $origins = @('http://localhost:8081', 'http://127.0.0.1:8081')
    $lan = Get-LanIPv4
    if ($lan) {
        $origins += "http://${lan}:8081"
    }
    $env:CORS_ALLOWED_ORIGINS = $origins -join ','
}

function Test-DemoCodeList {
    param([AllowNull()][object]$Value)

    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $false
    }

    if ($text.TrimStart().StartsWith('[')) {
        try {
            $codes = @($text | ConvertFrom-Json -ErrorAction Stop)
        }
        catch {
            return $false
        }
    }
    else {
        $codes = @($text -split ',')
    }

    return @($codes | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count -gt 0
}

function Assert-DemoProfileConfiguration {
    $missingKeys = @()
    if ([string]::IsNullOrWhiteSpace($env:CONSENT_POLICY_VERSION)) {
        $missingKeys += 'CONSENT_POLICY_VERSION'
    }
    if (-not (Test-DemoCodeList $env:ONBOARDING_PRIMARY_GOAL_CODES)) {
        $missingKeys += 'ONBOARDING_PRIMARY_GOAL_CODES'
    }
    if (-not (Test-DemoCodeList $env:ONBOARDING_EXPERIENCE_LEVEL_CODES)) {
        $missingKeys += 'ONBOARDING_EXPERIENCE_LEVEL_CODES'
    }

    if ($missingKeys.Count -gt 0) {
        throw "Missing required demo configuration keys: $($missingKeys -join ', ')"
    }
}

function Invoke-Psql {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Statement
    )
    # ON_ERROR_STOP makes psql exit non-zero on a failed statement; without it a
    # failure would be reported as success.
    Invoke-Native $Description {
        docker exec $ContainerName psql -U exercise_app -d $Database `
            -v ON_ERROR_STOP=1 -q -c $Statement
    }
}

function Start-Database {
    $existing = docker ps -a --filter "name=^/$ContainerName$" --format '{{.Names}}'
    if ($existing -eq $ContainerName) {
        docker start $ContainerName | Out-Null
        Write-Host "Reusing existing container $ContainerName"
    }
    else {
        docker run -d --name $ContainerName `
            -e POSTGRES_USER=exercise_app `
            -e POSTGRES_PASSWORD=local_dev_only `
            -e POSTGRES_DB=$DemoDatabase `
            -p "${HostPort}:5432" postgres:16 | Out-Null
        Write-Host "Started PostgreSQL 16 as $ContainerName on port $HostPort"
    }

    $ready = $false
    foreach ($attempt in 1..60) {
        docker exec $ContainerName pg_isready -U exercise_app -d $DemoDatabase 2>$null | Out-Null
        if ($?) {
            Write-Host "PostgreSQL ready after ${attempt}s"
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        throw 'PostgreSQL did not become ready in 60s'
    }
    $global:LASTEXITCODE = 0
}

function Reset-TestDatabase {
    # WITH (FORCE) terminates sessions a previous run left open. Without it the
    # drop fails, the stale database survives, and tests that assume empty
    # catalog lookup tables fail for reasons unrelated to the code under test.
    Invoke-Psql -Description "Drop $TestDatabase" -Database 'postgres' `
        -Statement "DROP DATABASE IF EXISTS $TestDatabase WITH (FORCE);"
    Invoke-Psql -Description "Create $TestDatabase" -Database 'postgres' `
        -Statement "CREATE DATABASE $TestDatabase OWNER exercise_app;"
}

function Show-ApiAddresses {
    $lan = Get-LanIPv4

    Write-Host ''
    Write-Host 'Set EXPO_PUBLIC_API_BASE_URL in frontend/.env.local to the address'
    Write-Host 'reachable from the device running the app (no /api/v1 suffix):'
    Write-Host '  Web / iOS simulator    http://127.0.0.1:8000'
    Write-Host '  Android emulator       http://10.0.2.2:8000'
    if ($lan) {
        Write-Host "  Physical device        http://${lan}:8000"
    }
    Write-Host ''
    Write-Host 'In a browser use 127.0.0.1, not localhost: uvicorn binds IPv4 only'
    Write-Host 'and browsers try localhost as ::1 (IPv6) first.'
    Write-Host ''
}

function Set-AppApiBaseUrl {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $envPath = Join-Path $RepoRoot 'frontend/.env.local'
    if (-not (Test-Path $envPath)) {
        throw "frontend/.env.local not found. Copy frontend/.env.example first."
    }
    $lines = Get-Content $envPath
    $updated = $lines | ForEach-Object {
        if ($_ -match '^\s*EXPO_PUBLIC_API_BASE_URL\s*=') {
            "EXPO_PUBLIC_API_BASE_URL=$BaseUrl"
        }
        else { $_ }
    }
    Set-Content -Path $envPath -Value $updated -Encoding utf8
}

switch ($Command) {
    'up' {
        Set-DemoEnvironment
        Start-Database
        Invoke-Native 'Sync Python dependencies' { uv sync --frozen --group dev }
        Invoke-Native 'Apply migrations' { uv run alembic -c backend/alembic.ini upgrade head }
        Invoke-Native 'Install synthetic demo catalog' { uv run python -m backend.scripts.demo_seed seed }
        Show-ApiAddresses
        Write-Host 'Next: .\scripts\demo-local.ps1 api'
    }

    'api' {
        Set-DemoEnvironment
        Assert-DemoProfileConfiguration
        if (-not $env:FIREBASE_PROJECT_ID) {
            Write-Warning ('FIREBASE_PROJECT_ID is not set. Authentication will fail closed ' +
                'with 503 AUTH_PROVIDER_UNAVAILABLE. Set it, and point ' +
                'GOOGLE_APPLICATION_CREDENTIALS at a service-account file outside this repo.')
        }
        Show-ApiAddresses
        uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
    }

    'share' {
        # The LAN address changes with the network, and a stale value in
        # .env.local or in the backend's allowed origins fails as a plain
        # "cannot reach the server", so both are refreshed together here.
        $lan = Get-LanIPv4
        if (-not $lan) {
            throw 'No LAN IPv4 address found. Connect to a network first.'
        }
        Set-AppApiBaseUrl "http://${lan}:8000"
        Write-Host "Set EXPO_PUBLIC_API_BASE_URL to http://${lan}:8000"
        Write-Host ''

        $rules = @(Get-NetFirewallRule -DisplayName 'helkki demo*' -ErrorAction SilentlyContinue)
        if ($rules.Count -eq 0) {
            Write-Warning ('Windows Firewall has no inbound rule for 8000/8081, so teammates ' +
                'will not connect. Run this once in an ADMIN PowerShell:')
            Write-Host ''
            Write-Host '  New-NetFirewallRule -DisplayName "helkki demo (api)" -Direction Inbound `'
            Write-Host '    -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private'
            Write-Host '  New-NetFirewallRule -DisplayName "helkki demo (expo)" -Direction Inbound `'
            Write-Host '    -LocalPort 8081 -Protocol TCP -Action Allow -Profile Private'
            Write-Host ''
        }
        else {
            Write-Host 'Firewall rules present.'
            Write-Host ''
        }

        Write-Host 'Now restart BOTH, so the backend picks up the new allowed origin'
        Write-Host 'and the app rebuilds with the new API address:'
        Write-Host '  terminal 1:  .\scripts\demo-local.ps1 api'
        Write-Host '  terminal 2:  npx expo start --web --port 8081 --clear'
        Write-Host ''
        Write-Host "Then share with teammates on the same network:"
        Write-Host "  http://${lan}:8081"
    }

    'seed' {
        Set-DemoEnvironment
        Invoke-Native 'Install synthetic demo catalog' { uv run python -m backend.scripts.demo_seed seed }
    }

    'reset' {
        Set-DemoEnvironment
        Invoke-Native 'Reset demo data' { uv run python -m backend.scripts.demo_seed reset }
        Write-Host 'Demo users deleted. Sign in again in the app to restart from onboarding.'
    }

    'rules' {
        # The synthetic seed carries no safety rules, so a check-in that reports
        # discomfort evaluates with no rule set and fails closed (FAILED). This
        # loads the reviewed rule bundle and activates the catalog that carries
        # it. The catalog itself has no recorded domain review, so activation
        # needs the demo-only override and must stay on the demo database.
        Set-DemoEnvironment
        Invoke-Native 'Load catalog bundle' {
            uv run python -m backend.scripts.catalog_data_load load
        }
        Invoke-Native 'Activate rule-carrying catalog' {
            uv run python -m backend.scripts.catalog_activate activate $RuleCatalogVersion `
                --demo-unreviewed
        }
        Write-Host ''
        Write-Host 'The synthetic catalog is now DEPRECATED, so routines built on it no'
        Write-Host 'longer produce decisions. Run reset and sign in again:'
        Write-Host '  .\scripts\demo-local.ps1 reset   # re-seeds the synthetic catalog'
        Write-Host '  .\scripts\demo-local.ps1 rules   # then re-run this command'
    }

    'test' {
        Set-DemoEnvironment
        Start-Database
        Reset-TestDatabase
        Invoke-Native 'Backend lint' { uv run ruff check backend data/scripts }
        Invoke-Native 'Backend format check' { uv run ruff format --check backend data/scripts }
        Invoke-Native 'Backend type check' { uv run mypy }
        Invoke-Native 'Backend tests' { uv run pytest }
        Set-Location (Join-Path $RepoRoot 'frontend')
        try {
            Invoke-Native 'Frontend format check' { npm run format:check }
            Invoke-Native 'Frontend lint' { npm run lint }
            Invoke-Native 'Frontend type check' { npm run typecheck }
            Invoke-Native 'Frontend tests' { npm test }
        }
        finally {
            Set-Location $RepoRoot
        }
        Write-Host ''
        Write-Host 'All verification commands passed.'
    }

    'psql' {
        docker exec -it $ContainerName psql -U exercise_app -d $DemoDatabase
    }

    'down' {
        docker rm -f $ContainerName 2>$null | Out-Null
        $global:LASTEXITCODE = 0
        Write-Host "Removed $ContainerName. Both demo and test databases are gone."
    }
}
