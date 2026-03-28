$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$backendEnv = Join-Path $backendDir ".env"
$frontendNodeModules = Join-Path $frontendDir "node_modules"

function Test-LocalPortInUse {
    param([int]$Port)

    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    }
    catch {
        return $false
    }
}

if (-not (Test-Path $pythonExe)) {
    throw "Missing .venv\\Scripts\\python.exe. Create the virtual environment and install backend dependencies first."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found on PATH. Install Node.js 18+ first."
}

if (-not (Test-Path $backendEnv)) {
    Write-Warning "backend/.env is missing. Copy backend/.env.example to backend/.env if you need Gemini or custom settings."
}

if (-not (Test-Path $frontendNodeModules)) {
    Write-Host "frontend/node_modules not found. Installing frontend dependencies..."
    Push-Location $frontendDir
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

if (Test-LocalPortInUse 8000) {
    Write-Host "Backend already listening at http://127.0.0.1:8000"
}
else {
    Start-Process powershell -WorkingDirectory $repoRoot -ArgumentList @(
        "-NoExit",
        "-Command",
        "& '$pythonExe' -m uvicorn app.main:app --app-dir '$backendDir' --host 127.0.0.1 --port 8000 --reload"
    ) | Out-Null

    Write-Host "Backend window started at http://127.0.0.1:8000"
}

if (Test-LocalPortInUse 3000) {
    Write-Host "Frontend already listening at http://localhost:3000"
}
else {
    Start-Process powershell -WorkingDirectory $frontendDir -ArgumentList @(
        "-NoExit",
        "-Command",
        "npm run dev"
    ) | Out-Null

    Write-Host "Frontend window started at http://localhost:3000"
}

Write-Host "Swagger UI: http://127.0.0.1:8000/docs"