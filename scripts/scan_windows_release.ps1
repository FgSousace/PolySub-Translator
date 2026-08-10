param(
    [Parameter(Mandatory = $true)]
    [string[]]$Paths
)

$ErrorActionPreference = "Stop"

try {
    $defenderStatus = Get-MpComputerStatus -ErrorAction Stop
} catch {
    Write-Warning "Microsoft Defender nie jest dostępny na tym runnerze: $($_.Exception.Message)"
    exit 0
}

if (-not $defenderStatus.AntivirusEnabled) {
    Write-Warning "Microsoft Defender jest wyłączony na tym runnerze; skan został pominięty."
    exit 0
}

$platformRoot = Join-Path $env:ProgramData "Microsoft\Windows Defender\Platform"
$defender = Get-ChildItem -Path $platformRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $defender) {
    $fallback = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
    if (Test-Path $fallback) {
        $defender = $fallback
    }
}
if (-not $defender) {
    throw "Microsoft Defender jest aktywny, ale nie znaleziono MpCmdRun.exe."
}

& $defender -SignatureUpdate
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Nie udało się odświeżyć sygnatur Defendera; używam sygnatur runnera."
}

foreach ($path in $Paths) {
    $resolved = (Resolve-Path $path).Path
    Write-Host "Skanowanie Microsoft Defender: $resolved"
    & $defender -Scan -ScanType 3 -File $resolved -DisableRemediation
    if ($LASTEXITCODE -eq 2) {
        throw "Defender wykrył zagrożenie/PUA albo błąd skanowania w pliku: $resolved"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Skan Defendera zakończył się kodem $LASTEXITCODE dla pliku: $resolved"
    }
}

Write-Host "Microsoft Defender nie wykrył zagrożeń w plikach wydania."
