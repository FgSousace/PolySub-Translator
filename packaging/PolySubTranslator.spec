from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)


PROJECT_ROOT = Path(SPECPATH).parent

datas = [
    (str(PROJECT_ROOT / "LICENSE"), "."),
    (str(PROJECT_ROOT / "NOTICE.txt"), "."),
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(PROJECT_ROOT / "docs" / "INSTRUKCJA_OBSLUGI_PL.md"), "."),
    (str(PROJECT_ROOT / "packaging" / "amd_worker_entry.py"), "amd-worker"),
    (str(PROJECT_ROOT / "packaging" / "narrator_worker_entry.py"), "narrator-worker"),
    (str(PROJECT_ROOT / "src" / "polysub"), "amd-worker/src/polysub"),
]
binaries = []
hiddenimports = [
    "fasttext",
    "numpy",
    "sentencepiece",
    "tiktoken",
    "torch",
]
datas += collect_data_files("transformers")

# These packages use compiled extensions and/or runtime discovery. Collecting
# their complete package payload prevents a build from passing while the local
# model fails only after the user presses "Rozpocznij tłumaczenie".
for package in (
    "huggingface_hub",
    "tokenizers",
    "safetensors",
    "sentencepiece",
    "tiktoken",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for package in ("av", "ctranslate2", "faster_whisper", "imageio_ffmpeg"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for distribution in (
    "polysub-translator",
    "torch",
    "transformers",
    "tokenizers",
    "safetensors",
    "huggingface-hub",
    "sentencepiece",
    "tiktoken",
    "fasttext-wheel",
    "av",
    "ctranslate2",
    "faster-whisper",
    "imageio-ffmpeg",
    "onnxruntime",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        # Some packages do not expose metadata in every installation layout.
        # Their code is still collected by Analysis and the standard hooks.
        pass

hiddenimports += collect_submodules("fasttext")
for transformer_package in (
    "generation",
    "models.m2m_100",
    "models.nllb",
    "models.mbart",
    "models.marian",
    "models.t5",
):
    hiddenimports += collect_submodules(f"transformers.{transformer_package}")

a = Analysis(
    [str(PROJECT_ROOT / "packaging" / "windows_entry.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PROJECT_ROOT / "packaging" / "runtime_cuda.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PolySubTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=str(PROJECT_ROOT / "packaging" / "version_info.txt"),
)

app = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PolySubTranslator",
)
