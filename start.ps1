$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$LogDir = Join-Path $ProjectRoot 'logs'
$BundledPython = (Get-Command python -ErrorAction Stop).Source
$BundledNode = (Get-Command node -ErrorAction Stop).Source
$BundledPnpm = (Get-Command pnpm -ErrorAction Stop).Source
$BackendPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$ViteScript = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $BackendPython)) {
  Write-Host 'First run: preparing backend...'
  & $BundledPython -m venv (Join-Path $BackendDir '.venv')
  & $BackendPython -m pip install -r (Join-Path $BackendDir 'requirements.txt')
}
if (-not (Test-Path $ViteScript)) {
  Write-Host 'First run: installing frontend dependencies...'
  & $BundledPnpm install --dir $FrontendDir
}

$ApiRunning = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if (-not $ApiRunning) {
  Start-Process -FilePath $BackendPython `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8010' `
    -WorkingDirectory $BackendDir -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir 'backend.log') `
    -RedirectStandardError (Join-Path $LogDir 'backend-error.log')
}

$WebRunning = Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue
if (-not $WebRunning) {
  Start-Process -FilePath $BundledNode `
    -ArgumentList $ViteScript, '--host', '127.0.0.1', '--port', '4173' `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir 'frontend.log') `
    -RedirectStandardError (Join-Path $LogDir 'frontend-error.log')
}

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
  try {
    $Api = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8010/api/health' -TimeoutSec 2
    $Web = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:4173' -TimeoutSec 2
    if ($Api.StatusCode -eq 200 -and $Web.StatusCode -eq 200) { $Ready = $true; break }
  } catch {
    Start-Sleep -Seconds 1
  }
}

if (-not $Ready) {
  Write-Host 'Startup failed. Check these log files:' -ForegroundColor Red
  Write-Host (Join-Path $LogDir 'backend-error.log')
  Write-Host (Join-Path $LogDir 'frontend-error.log')
  exit 1
}

$Url = 'http://127.0.0.1:4173'
Write-Host "AI Fund Assistant is ready: $Url" -ForegroundColor Green
Start-Process $Url
