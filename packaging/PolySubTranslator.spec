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
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = [
    "fasttext",
    "numpy",
    "sentencepiece",
    "torch",
]
for package in ("transformers", "huggingface_hub", "tokenizers", "safetensors"):
    datas += collect_data_files(package)

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
for model_package in ("m2m_100", "nllb", "mbart", "marian", "t5"):
    hiddenimports += collect_submodules(f"transformers.models.{model_package}")

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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

app = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PolySubTranslator",
)
