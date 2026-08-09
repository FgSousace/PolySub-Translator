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
$traceFile = Join-Path `
    ([IO.Path]::GetTempPath()) `
    ("polysub-self-test-" + [guid]::NewGuid().ToString("N") + ".log")
$previousTraceFile = $env:POLYSUB_SELF_TEST_TRACE
$env:POLYSUB_SELF_TEST_TRACE = $traceFile
Write-Host "Uruchamianie testu: $displayName (limit: $TimeoutSeconds s)"

try {
    $process = Start-Process `
        -FilePath $executablePath `
        -ArgumentList $Argument `
        -PassThru

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        if (Test-Path $traceFile) {
            Write-Host "Ostatnie etapy aplikacji przed przekroczeniem limitu:"
            Get-Content $traceFile | Write-Host
        }
        throw "Test $displayName przekroczył limit $TimeoutSeconds sekund."
    }

    if ($process.ExitCode -ne 0) {
        if (Test-Path $traceFile) {
            Write-Host "Szczegóły błędu aplikacji:"
            Get-Content $traceFile | Write-Host
        }
        throw "Test $displayName zakończył się kodem $($process.ExitCode)."
    }

    Write-Host "Test zakończony poprawnie: $displayName"
}
finally {
    Remove-Item $traceFile -Force -ErrorAction SilentlyContinue
    if ($null -eq $previousTraceFile) {
        Remove-Item Env:POLYSUB_SELF_TEST_TRACE -ErrorAction SilentlyContinue
    }
    else {
        $env:POLYSUB_SELF_TEST_TRACE = $previousTraceFile
    }
}
