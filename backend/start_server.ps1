# Server startup script with validation
Write-Host "`n=== CRM Backend Server Startup ===" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "❌ ERROR: .env file not found" -ForegroundColor Red
    Write-Host "Please create .env file with your configuration" -ForegroundColor Yellow
    exit 1
}

# Validate environment
Write-Host "`nValidating environment..." -ForegroundColor Yellow
python check_env.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ Environment validation failed" -ForegroundColor Red
    Write-Host "Please fix the errors above before starting the server" -ForegroundColor Yellow
    exit 1
}

# Clear any system environment variables that might conflict
Write-Host "`nClearing system environment variables..." -ForegroundColor Yellow
Remove-Item Env:\OPENAI_API_KEY -ErrorAction SilentlyContinue

# Start server
Write-Host "`nStarting server..." -ForegroundColor Green
uvicorn server:app --reload --host 0.0.0.0 --port 8000
