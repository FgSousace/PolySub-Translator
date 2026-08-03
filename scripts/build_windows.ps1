param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repositoryRoot

if (-not $SkipDependencyInstall) {
    python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się zaktualizować pip."
    }

    python -m pip install -e ".[local,fasttext,video,build]"
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się zainstalować zależności do budowania."
    }
}

python -m PyInstaller --noconfirm --clean "packaging\PolySubTranslator.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller nie utworzył aplikacji."
}

$innoCompiler = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($innoCompiler) {
    $innoCompilerPath = $innoCompiler.Source
} else {
    $innoCompilerPath = Join-Path `
        ([Environment]::GetFolderPath("ProgramFilesX86")) `
        "Inno Setup 6\ISCC.exe"
}

if (-not (Test-Path $innoCompilerPath)) {
    throw "Nie znaleziono Inno Setup 6. Zainstaluj go z https://jrsoftware.org/isdl.php"
}

& $innoCompilerPath "packaging\PolySubTranslator.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup nie utworzył instalatora."
}

Write-Host "Gotowe: installer-output\PolySub-Translator-Setup.exe"
