Write-Host "Starting CRM Application in CONFIG-BASED DUAL TUNNEL MODE..." -ForegroundColor Cyan

# Get the script's directory
$ScriptPath = $PSScriptRoot

# Stop existing processes
Write-Host "Cleaning up old processes..." -ForegroundColor Yellow
Stop-Process -Name "python", "node", "ngrok" -ErrorAction SilentlyContinue

# Ensure TUNNEL_MODE is NOT forced to true (we want local DB)
$env:TUNNEL_MODE = "false"

# 1. Start Backend Server
Write-Host "Launching Backend Server on port 8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\backend'; `$env:TUNNEL_MODE='false'; uvicorn server:app --host 127.0.0.1 --port 8000"

# 2. Start Unified ngrok Tunnel (Port 8000 and 8081)
Write-Host "Launching unified ngrok tunnel..." -ForegroundColor Green
$NgrokPath = "C:\Users\sarch\AppData\Local\Microsoft\WindowsApps\ngrok.exe"
# Start both tunnels using the config file
Start-Process $NgrokPath -ArgumentList "start", "--all", "--config", "$ScriptPath\ngrok_config.yml"

Write-Host "`nWaiting for tunnels to stabilize..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 3. Capture and Configure URLs
Write-Host "Configuring Tunnels..." -ForegroundColor Yellow
try {
    $TunnelsResponse = Invoke-RestMethod http://localhost:4040/api/tunnels
    
    # Capture Backend
    $BackendUrl = ($TunnelsResponse.tunnels | Where-Object { $_.name -eq "backend" -and $_.proto -eq "https" } | Select-Object -First 1).public_url
    if (-not $BackendUrl) { $BackendUrl = ($TunnelsResponse.tunnels | Where-Object { $_.name -eq "backend" } | Select-Object -First 1).public_url }
    
    # Capture Frontend
    $FrontendUrl = ($TunnelsResponse.tunnels | Where-Object { $_.name -eq "frontend" -and $_.proto -eq "https" } | Select-Object -First 1).public_url
    if (-not $FrontendUrl) { $FrontendUrl = ($TunnelsResponse.tunnels | Where-Object { $_.name -eq "frontend" } | Select-Object -First 1).public_url }
    
    $FrontendHost = $FrontendUrl -replace "https://", ""
    
    Write-Host "Backend URL: $BackendUrl" -ForegroundColor Green
    Write-Host "Frontend URL: $FrontendUrl" -ForegroundColor Green

    # Update backend configuration in frontend/.env
    $EnvPath = "$ScriptPath\frontend\.env"
    if (Test-Path $EnvPath) {
        $Content = Get-Content $EnvPath
        $NewContent = $Content -replace "EXPO_PUBLIC_BACKEND_URL=.*", "EXPO_PUBLIC_BACKEND_URL=$BackendUrl"
        $NewContent | Set-Content $EnvPath
        Write-Host "Updated frontend/.env with Backend URL" -ForegroundColor Green
    }
    
} catch {
    Write-Host "Failed to capture ngrok URLs. Please check the ngrok window." -ForegroundColor Red
}

# 4. Start Frontend
Write-Host "Launching Frontend (Expo Local + Manual Tunnel)..." -ForegroundColor Green
Write-Host "FORCING EXPO TO USE HOST: $FrontendHost" -ForegroundColor Green
# We set the environment variable so Expo uses our tunnel host for the QR code
# Using -NoExit and explicit env setting in the command string
$ExpoCommand = "cd '$ScriptPath\frontend'; `$env:REACT_NATIVE_PACKAGER_HOSTNAME='$FrontendHost'; `$env:EXPO_PACKAGER_PROXY_URL='$FrontendUrl'; npx expo start --port 8081"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $ExpoCommand

Write-Host "`nReady to develop! Scan the QR code in the Expo window." -ForegroundColor Cyan
Write-Host "The QR code SHOULD point to: exp://$FrontendHost" -ForegroundColor Green
Write-Host "If scan fails, manually enter this in Expo Go: exp://$FrontendHost" -ForegroundColor Cyan
