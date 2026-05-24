$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$serverScript = Join-Path $root "gui_server.py"
$url = "http://127.0.0.1:7860"

function Stop-ExistingServer {
    $portLine = netstat -ano 2>$null | Select-String ":7860\s.*LISTENING"
    if ($portLine) {
        $oldPid = ($portLine -split "\s+")[-1]
        if ($oldPid -match "^\d+$") {
            Write-Host "Killing existing server (PID $oldPid)..."
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
        }
    }
}

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    Write-Host "No .venv Python found, falling back to current python."
    $python = "python"
}

Stop-ExistingServer

# Open browser in background after a short delay
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process $using:url
} | Out-Null

Write-Host "Starting server... ($url)"
Write-Host "Press Ctrl+C to stop.`n"

# Run server in foreground so output is visible
& $python $serverScript
