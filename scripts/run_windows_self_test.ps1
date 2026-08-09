param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,

    [Parameter(Mandatory = $true)]
    [string]$Argument,

    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$executablePath = (Resolve-Path $Executable).Path
$displayName = "$([IO.Path]::GetFileName($executablePath)) $Argument"
Write-Host "Uruchamianie testu: $displayName (limit: $TimeoutSeconds s)"

$process = Start-Process `
    -FilePath $executablePath `
    -ArgumentList $Argument `
    -PassThru

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Test $displayName przekroczył limit $TimeoutSeconds sekund."
}

if ($process.ExitCode -ne 0) {
    throw "Test $displayName zakończył się kodem $($process.ExitCode)."
}

Write-Host "Test zakończony poprawnie: $displayName"
