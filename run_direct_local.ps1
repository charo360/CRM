Write-Host "Starting CRM Application in DIRECT LOCAL MODE (VPN Closed)..." -ForegroundColor Cyan

# Get the script's directory
$ScriptPath = $PSScriptRoot

# Stop existing processes
Write-Host "Cleaning up old processes..." -ForegroundColor Yellow
Stop-Process -Name "python", "node", "ngrok" -ErrorAction SilentlyContinue

# Ensure TUNNEL_MODE is false
$env:TUNNEL_MODE = "false"

# Start Backend (explicitly on 0.0.0.0)
Write-Host "Launching Backend Server on 0.0.0.0:8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\backend'; `$env:TUNNEL_MODE='false'; uvicorn server:app --host 0.0.0.0 --port 8000"

# Start Frontend (Standard Expo)
Write-Host "Launching Frontend (Standard Expo)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\frontend'; npx expo start"

Write-Host "`nApplication starting! Ensure your phone is on the Wi-Fi: 10.1.10.x" -ForegroundColor Yellow
Write-Host "If the phone cannot connect, your Wi-Fi may block Device-to-Device traffic." -ForegroundColor Red
