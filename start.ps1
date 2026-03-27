param(
    [string]$ScanDir = "C:\src\Teams-Graph"
)

$Root   = $PSScriptRoot
$TuiDir = "$Root\tui"

# --- Virtual environment setup ---
if (-not (Test-Path "$TuiDir\.venv")) {
    Write-Host "[tui] Creating virtual environment..."
    python -m venv "$TuiDir\.venv"
}

Write-Host "[tui] Installing dependencies..."
& "$TuiDir\.venv\Scripts\pip.exe" install -r "$TuiDir\requirements.txt" -q

Write-Host "[tui] Scanning agents from: $ScanDir"
Write-Host "[tui] Launching Agent Runner..."
& "$TuiDir\.venv\Scripts\python.exe" "$TuiDir\app.py" --scan-dir "$ScanDir"
