# Starts the Brainwise backend with the API key from .env, overriding any
# stray OPENAI_API_KEY (e.g. a Gemini key) inherited from the shell.
# Usage, from backend/:   powershell -ExecutionPolicy Bypass -File .\start_backend.ps1

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) { Write-Error ".env not found at $envFile"; exit 1 }

$line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^openai_api_key=' } | Select-Object -First 1
if (-not $line) { Write-Error 'openai_api_key missing from .env'; exit 1 }

$env:OPENAI_API_KEY = ($line -replace '^openai_api_key=', '').Trim()
if (-not $env:OPENAI_API_KEY.StartsWith('sk-')) { Write-Error 'openai_api_key in .env does not look like an OpenAI key'; exit 1 }

Write-Host "OPENAI_API_KEY forced from .env (prefix $($env:OPENAI_API_KEY.Substring(0, 7))...)" -ForegroundColor Green
Set-Location -LiteralPath $PSScriptRoot
uv run uvicorn backend.main:app --reload
