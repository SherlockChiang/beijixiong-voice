$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$serverScript = Join-Path $root "gui_server.py"
$url = "http://127.0.0.1:7860"

function Test-GuiServer {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/config" -TimeoutSec 1
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-PortInUse {
    $portLine = netstat -ano 2>$null | Select-String ":7860\s.*LISTENING"
    return [bool]$portLine
}

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    Write-Host "No .venv Python found, falling back to current python."
    $python = "python"
}

if (Test-GuiServer) {
    Start-Process $url
    Write-Host "Beijixiong Voice GUI already running: $url"
    exit 0
}

if (Test-PortInUse) {
    throw "Port 7860 is already in use by another process. Stop it or change the server port before starting the GUI."
}

# Open browser in background after a short delay
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process $using:url
} | Out-Null

Write-Host "Starting server... ($url)"
Write-Host "Press Ctrl+C to stop.`n"

# Run server in foreground so output is visible
& $python $serverScript
