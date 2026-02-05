Write-Host "Starting CRM Application..." -ForegroundColor Cyan

# Get the script's directory to ensure we use absolute paths relative to this script
$ScriptPath = $PSScriptRoot

# Start Backend
Write-Host "Launching Backend Server..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\backend'; .\start_server.ps1"

# Start Frontend
Write-Host "Launching Frontend (Expo)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\frontend'; npm start"

Write-Host "Application started! Check the new windows." -ForegroundColor Cyan
