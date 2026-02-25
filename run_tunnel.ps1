Write-Host "Starting CRM Application in TUNNEL MODE..." -ForegroundColor Cyan
Write-Host "This mode uses MongoDB Data API (HTTPS) and Expo Tunnel to bypass restricted networks." -ForegroundColor Cyan

# Get the script's directory
$ScriptPath = $PSScriptRoot

# Set Tunnel Mode Environment Variable
$env:TUNNEL_MODE = "true"

# Start Backend
Write-Host "Launching Backend Server (Tunnel Mode enabled)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\backend'; `$env:TUNNEL_MODE='true'; .\start_server.ps1"

# Start Frontend
Write-Host "Launching Frontend (Expo Tunnel)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\frontend'; npx expo start --tunnel"

Write-Host "Application starting! Ensure you have configured MONGO_DATA_API credentials in backend/.env" -ForegroundColor Yellow
