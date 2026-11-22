# Smoke: swiezy venv + requirements.txt (bez dev) + start.bat na malym wejsciu.
# Uzycie: powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
# Zgodne z Windows PowerShell 5.1 i pwsh.
$ErrorActionPreference = 'Stop'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('odw2json-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$oldPath = $env:PATH
$oldMode = $env:LLM_MODE
$failure = $null

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Polecenie zakonczone kodem ${LASTEXITCODE}: $Exe $($Arguments -join ' ')" }
}

try {
    Invoke-Native 'python' @('-m', 'venv', (Join-Path $tmp 'venv'))
    $vbin = Join-Path $tmp 'venv\Scripts'
    $vpy = Join-Path $vbin 'python.exe'
    Invoke-Native $vpy @('-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '-r', (Join-Path $repo 'requirements.txt'), '-c', (Join-Path $repo 'requirements-lock.txt'))

    $in = Join-Path $tmp 'in'
    $out = Join-Path $tmp 'out'
    $case = Join-Path $in 'case1'
    New-Item -ItemType Directory -Path $case, $out | Out-Null
    foreach ($n in 'odwolanie', 'pelnomocnictwo', 'potwierdzenie_przelewu') {
        Copy-Item (Join-Path $repo "data\train\przyklad_01\$n.pdf") (Join-Path $case "$n.pdf")
    }
    Copy-Item -LiteralPath (Join-Path $repo 'data\train\negatywne\KIO_KIO 2617-21.pdf') -Destination (Join-Path $case 'KIO_KIO 2617-21.pdf')

    # start.bat robi cd /d do swojego katalogu -> sciezki musza byc ABSOLUTNE.
    $env:PATH = "$vbin;$oldPath"
    $env:LLM_MODE = 'replay'
    & (Join-Path $repo 'start.bat') $in $out
    if ($LASTEXITCODE -ne 0) { throw "start.bat zwrocil kod $LASTEXITCODE" }

    $res = Join-Path $out 'case1'
    $files = @(Get-ChildItem -LiteralPath $res -Filter '*.json' -File)
    if ($files.Count -ne 4) { throw "Oczekiwano 4 plikow JSON, jest $($files.Count): $($files.Name -join ', ')" }

    $negPath = Join-Path $res 'KIO_KIO 2617-21.json'
    if (-not (Test-Path -LiteralPath $negPath)) { throw 'Brak JSON dla negatywu' }
    $negText = [System.IO.File]::ReadAllText($negPath, [System.Text.Encoding]::UTF8)
    if ($negText.Trim() -ne '{}') { throw "Negatyw nie jest {}: $negText" }

    $expect = @{ 'odwolanie' = 'OdwolanieKIO'; 'pelnomocnictwo' = 'mocodawca'; 'potwierdzenie_przelewu' = 'przelew_bankowy' }
    foreach ($name in $expect.Keys) {
        $p = Join-Path $res "$name.json"
        $text = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
        try { $obj = $text | ConvertFrom-Json } catch { throw "$name.json nie jest poprawnym JSON" }
        if (-not ($obj.PSObject.Properties.Name -contains $expect[$name])) { throw "$name.json bez klucza $($expect[$name])" }
    }
} catch {
    $failure = $_.Exception.Message
} finally {
    $env:PATH = $oldPath
    $env:LLM_MODE = $oldMode
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

$sw.Stop()
$secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
if ($failure) {
    Write-Host "SMOKE FAIL ($secs s): $failure"
    exit 1
}
Write-Host "SMOKE PASS ($secs s)"
exit 0
