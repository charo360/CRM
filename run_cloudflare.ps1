Write-Host "Starting CRM Application using CLOUDFLARE TUNNEL (Double Tunnel)..." -ForegroundColor Cyan

# Get the script's directory
$ScriptPath = $PSScriptRoot

# Stop existing processes
Write-Host "Cleaning up old processes..." -ForegroundColor Yellow
Stop-Process -Name "python", "node", "cloudflared" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Path to cloudflared
$CloudflaredPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

# Start Backend Cloudflare Tunnel
Write-Host "Launching Cloudflare Tunnel for BACKEND (port 8000)..." -ForegroundColor Green
Start-Process "C:\Program Files (x86)\cloudflared\cloudflared.exe" -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000" -RedirectStandardError "$ScriptPath\cf_backend.log" -NoNewWindow

# Start Expo Cloudflare Tunnel
Write-Host "Launching Cloudflare Tunnel for EXPO (port 8081)..." -ForegroundColor Green
Start-Process $CloudflaredPath -ArgumentList "tunnel", "--url", "http://127.0.0.1:8081" -RedirectStandardError "$ScriptPath\cf_expo.log" -NoNewWindow

Write-Host "Waiting 10 seconds for tunnels to be assigned URLs..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Extract the Expo tunnel URL
$ExpoUrl = (Select-String -Path "$ScriptPath\cf_expo.log" -Pattern "trycloudflare.com" | Select-Object -First 1).Line -replace '.*\|.*?(https://\S+).*', '$1' -replace '\s+$', ''
if (-not $ExpoUrl -or -not $ExpoUrl.StartsWith("https://")) {
    Write-Host "WARNING: Could not auto-detect Expo tunnel URL. Check cf_expo.log manually." -ForegroundColor Red
    $ExpoUrl = "http://127.0.0.1:8081"
}
$ExpoHostname = $ExpoUrl -replace "https://", ""

# Extract backend tunnel URL
$BackendUrl = (Select-String -Path "$ScriptPath\cf_backend.log" -Pattern "trycloudflare.com" | Select-Object -First 1).Line -replace '.*\|.*?(https://\S+).*', '$1' -replace '\s+$', ''
if ($BackendUrl -and $BackendUrl.StartsWith("https://")) {
    Write-Host "Backend Tunnel LIVE at: $BackendUrl" -ForegroundColor Green
    # Update frontend .env
    $EnvFile = "$ScriptPath\frontend\.env"
    (Get-Content $EnvFile) -replace '^EXPO_PUBLIC_BACKEND_URL=.*', "EXPO_PUBLIC_BACKEND_URL=$BackendUrl" | Set-Content $EnvFile
    Write-Host "Updated frontend/.env with backend URL." -ForegroundColor Green
} else {
    Write-Host "WARNING: Could not auto-detect backend tunnel URL. Check cf_backend.log." -ForegroundColor Red
}

# Start Backend Server
Write-Host "Launching Backend Server on 127.0.0.1:8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\backend'; `$env:TUNNEL_MODE='false'; uvicorn server:app --host 127.0.0.1 --port 8000"

# Start Frontend with Cloudflare hostname so QR code uses the tunnel URL
Write-Host "Launching Frontend (Expo via Cloudflare, hostname: $ExpoHostname)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ScriptPath\frontend'; `$env:REACT_NATIVE_PACKAGER_HOSTNAME='$ExpoHostname'; npx expo start --port 8081 --host lan"

Write-Host "`n====================================================" -ForegroundColor Magenta
Write-Host "DOUBLE CLOUDFLARE TUNNEL IS STARTING" -ForegroundColor Magenta
Write-Host "  Backend URL : $BackendUrl" -ForegroundColor Yellow
Write-Host "  Expo URL    : $ExpoUrl" -ForegroundColor Yellow
Write-Host "Scan the QR code in the Expo window to connect." -ForegroundColor Cyan
Write-Host "====================================================`n" -ForegroundColor Magenta
