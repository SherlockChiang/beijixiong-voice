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

if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    Write-Host "No .venv Python found, falling back to current python."
    $python = "python"
}

if (-not (Test-GuiServer)) {
    Start-Process `
        -FilePath $python `
        -ArgumentList "`"$serverScript`"" `
        -WorkingDirectory $root `
        -WindowStyle Hidden

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-GuiServer) {
            $ready = $true
            break
        }
    }

    if (-not $ready) {
        throw "GUI server did not become ready at $url"
    }
}

Start-Process $url
Write-Host "Beijixiong Voice GUI opened: $url"
