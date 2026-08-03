from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


PROJECT_ROOT = Path(SPECPATH).parent

datas = []
for package in ("transformers", "huggingface_hub", "tokenizers", "safetensors"):
    datas += collect_data_files(package)

for distribution in (
    "polysub-translator",
    "torch",
    "transformers",
    "tokenizers",
    "safetensors",
    "huggingface-hub",
    "sentencepiece",
    "fasttext-wheel",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        # Some packages do not expose metadata in every installation layout.
        # Their code is still collected by Analysis and the standard hooks.
        pass

hiddenimports = [
    "fasttext",
    "numpy",
    "sentencepiece",
    "torch",
]
hiddenimports += collect_submodules("fasttext")
hiddenimports += collect_submodules("transformers.models.m2m_100")

a = Analysis(
    [str(PROJECT_ROOT / "packaging" / "windows_entry.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
