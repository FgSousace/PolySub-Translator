"""Windows DirectML backend for Whisper transcription.

The main PolySub process keeps using faster-whisper/CTranslate2 for CPU and
NVIDIA CUDA.  DirectML lives in a private Python runtime so its PyTorch build
cannot replace the ROCm/CUDA packages used by the rest of the application.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

TORCH_DIRECTML_VERSION = "0.2.5.dev240914"
DIRECTML_SAMPLE_COMMIT = "8700779fe7a09ea7a007cf3d7ab4293c78e41017"
DIRECTML_RUNTIME_SCHEMA = 1
DIRECTML_SAMPLE_ARCHIVE = (
    "https://github.com/microsoft/DirectML/archive/"
    f"{DIRECTML_SAMPLE_COMMIT}.zip"
)

_HOOKS_INSTALLED = False
_DIRECTML_DEVICE_NAMES: dict[int, str] = {}


class WhisperDirectMLError(RuntimeError):
    pass


def directml_runtime_directory() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    return parent / f"whisper-directml-runtime-{TORCH_DIRECTML_VERSION}"


def directml_runtime_python() -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    return directml_runtime_directory() / executable


def directml_model_cache() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    return parent / "whisper-directml-models"


def install_whisper_directml_hooks() -> None:
    """Attach DirectML to existing device discovery and video transcription."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return

    from . import compute_devices as compute_module
    from . import video as video_module

    original_detect = compute_module.detect_compute_devices
    original_transcribe = video_module.VideoSubtitleImporter._transcribe_audio

    def detect_with_directml(*args: Any, **kwargs: Any):
        devices = original_detect(*args, **kwargs)
        if os.name != "nt":
            return devices
        return _attach_directml_devices(devices)

    def transcribe_with_directml(
        importer: Any,
        video_path: Path,
        *,
        status: Any,
        progress: Any,
    ):
        configured = str(importer.device or os.getenv("POLYSUB_WHISPER_DEVICE", "cpu"))
        if not configured.casefold().startswith("directml"):
            return original_transcribe(
                importer,
                video_path,
                status=status,
                progress=progress,
            )

        try:
            return _transcribe_directml(
                importer,
                video_module,
                video_path,
                configured_device=configured,
                status=status,
                progress=progress,
            )
        except Exception as exc:
            if not importer.allow_cpu_fallback:
                if isinstance(exc, video_module.VideoImportError):
                    raise
                raise video_module.VideoImportError(
                    f"Whisper DirectML nie zakończył transkrypcji: {exc}"
                ) from exc

            status(
                "DirectML nie zakończył transkrypcji na GPU. "
                f"Przełączanie Whispera na CPU… Szczegóły: {str(exc)[-900:]}"
            )
            previous_device = importer.device
            importer.device = "cpu"
            try:
                return original_transcribe(
                    importer,
                    video_path,
                    status=status,
                    progress=progress,
                )
            finally:
                importer.device = previous_device

    detect_with_directml.__polysub_directml__ = True
    transcribe_with_directml.__polysub_directml__ = True
    compute_module.detect_compute_devices = detect_with_directml
    video_module.VideoSubtitleImporter._transcribe_audio = transcribe_with_directml
    _HOOKS_INSTALLED = True


def _attach_directml_devices(devices: list[Any]) -> list[Any]:
    """Advertise DirectML for Windows GPUs that do not already have CUDA transcription."""
    global _DIRECTML_DEVICE_NAMES
    _DIRECTML_DEVICE_NAMES = {}
    result: list[Any] = []
    gpu_ordinal = 0
    for device in devices:
        if getattr(device, "kind", "") != "gpu":
            result.append(device)
            continue

        _DIRECTML_DEVICE_NAMES[gpu_ordinal] = str(device.name)
        current_target = getattr(device, "transcription_target", None)
        # Keep faster-whisper CUDA on NVIDIA when it is available. DirectML is
        # primarily the Windows fallback for Radeon, Intel and other DX12 GPUs.
        if current_target:
            result.append(device)
            gpu_ordinal += 1
            continue

        backend_parts = {
            part.strip()
            for part in str(getattr(device, "backend", "")).split("+")
            if part.strip() and part.strip() != "wykryta przez system"
        }
        backend_parts.add("DirectML")
        safe_name = str(device.name).replace("|", " ")
        target = f"directml|{gpu_ordinal}|{safe_name}"
        result.append(
            replace(
                device,
                backend=" + ".join(sorted(backend_parts)),
                transcription_target=target,
                transcription_index=gpu_ordinal,
            )
        )
        gpu_ordinal += 1
    return result


def _resolve_directml_request(configured_device: str, fallback_index: int) -> tuple[int, str]:
    parts = configured_device.split("|", 2)
    index = max(int(fallback_index), 0)
    name = _DIRECTML_DEVICE_NAMES.get(index, "")
    if len(parts) >= 2:
        try:
            index = max(int(parts[1]), 0)
        except ValueError:
            pass
    if len(parts) == 3 and parts[2].strip():
        name = parts[2].strip()
    return index, name


def _resolve_model_alias(model_size: Any, model_name: str) -> str:
    from .whisper_models import WHISPER_MODEL_CATALOG

    if isinstance(model_size, str):
        normalized = model_size.strip().casefold()
        for spec in WHISPER_MODEL_CATALOG:
            if normalized in {spec.runtime_alias.casefold(), spec.id.casefold()}:
                return spec.runtime_alias

    normalized_name = str(model_name or "").strip().casefold()
    for spec in WHISPER_MODEL_CATALOG:
        if spec.display_name.casefold() in normalized_name:
            return spec.runtime_alias

    # The GUI normally supplies the display name, but Medium is the safest
    # default if an older settings file did not preserve the model identity.
    return "medium"


def _transcribe_directml(
    importer: Any,
    video_module: Any,
    video_path: Path,
    *,
    configured_device: str,
    status: Any,
    progress: Any,
):
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise WhisperDirectMLError("DirectML jest obsługiwany przez PolySub na Windows x64.")
    if importer.model_size is None:
        raise video_module.VideoImportError(
            "Film nie ma tekstowych napisów, a żaden model Whisper nie jest wybrany."
        )

    alias = _resolve_model_alias(importer.model_size, importer.model_name)
    device_index, device_name = _resolve_directml_request(
        configured_device,
        int(getattr(importer, "device_index", 0) or 0),
    )
    status(
        "Whisper DirectML: przygotowywanie prywatnego środowiska GPU "
        f"dla {device_name or f'urządzenia {device_index}'}…"
    )
    python_path = install_directml_runtime(status)
    ffmpeg = importer._resolve_ffmpeg()
    if ffmpeg is None:
        raise video_module.VideoImportError("Brakuje FFmpeg potrzebnego do przygotowania audio.")

    with TemporaryDirectory(prefix="polysub-whisper-dml-") as temporary_name:
        wav_path = Path(temporary_name) / "audio.wav"
        _extract_pcm_audio(ffmpeg, video_path, wav_path)
        status(
            f"Whisper {alias}: uruchamianie na GPU przez DirectML"
            + (f" — {device_name}" if device_name else "")
            + "…"
        )
        progress(0.0, 1.0)
        payload = _run_directml_worker(
            python_path,
            wav_path,
            model_alias=alias,
            device_index=device_index,
            device_name=device_name,
        )

    if not payload.get("ok"):
        raise WhisperDirectMLError(str(payload.get("error") or "worker DirectML zgłosił błąd"))

    actual_name = str(payload.get("device_name") or device_name or "GPU DirectML")
    mode = str(payload.get("mode") or "DirectML")
    status(f"Whisper: GPU aktywne — {actual_name} • DirectML • {mode}.")
    degraded = payload.get("degraded_reason")
    if degraded:
        status(f"Whisper DirectML: tryb zgodności — {str(degraded)[-600:]}")

    cues = []
    for item in payload.get("segments") or []:
        words = [
            SimpleNamespace(
                start=float(word.get("start") or 0.0),
                end=float(word.get("end") or 0.0),
                word=str(word.get("word") or ""),
            )
            for word in (item.get("words") or [])
            if isinstance(word, dict)
        ]
        segment = SimpleNamespace(
            start=float(item.get("start") or 0.0),
            end=float(item.get("end") or 0.0),
            text=str(item.get("text") or ""),
            words=words,
        )
        cues.extend(video_module._cues_from_segment(segment, first_identifier=len(cues) + 1))

    if not cues:
        raise video_module.VideoImportError(
            "Whisper DirectML nie znalazł mowy, z której można utworzyć napisy."
        )

    duration = max(
        (float(item.get("end") or 0.0) for item in payload.get("segments") or []),
        default=1.0,
    )
    progress(duration, duration)
    status("Zapisywanie rozpoznanych napisów SRT…")
    output = video_module.transcribed_subtitle_path(video_path)
    document = video_module.SRTDocument(cues=cues, source_path=output)
    document.save(output)
    return video_module.VideoImportResult(
        document=document,
        subtitle_path=output,
        method="transcribed",
        detected_language=str(payload.get("language") or "") or None,
    )


def _extract_pcm_audio(ffmpeg: str, video_path: Path, output: Path) -> None:
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise WhisperDirectMLError(f"Nie udało się uruchomić FFmpeg: {exc}") from exc
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size < 100:
        detail = (completed.stderr or b"").decode("utf-8", errors="replace")[-1000:]
        raise WhisperDirectMLError(f"Nie udało się wyciągnąć audio 16 kHz. {detail}")


def install_directml_runtime(status: Any = None) -> Path:
    status = status or (lambda _message: None)
    if os.name != "nt":
        raise WhisperDirectMLError("Prywatny runtime DirectML jest przeznaczony dla Windows.")

    from .amd_runtime import (
        _embedded_pip_ready,
        _embedded_python_core_ready,
        _install_embedded_python,
        _run_install_command,
    )

    runtime_dir = directml_runtime_directory()
    python_path = directml_runtime_python()
    if _directml_runtime_ready(python_path) and _manifest_matches():
        _write_worker_script(runtime_dir)
        status("Prywatne środowisko Whisper DirectML jest gotowe.")
        return python_path

    runtime_dir.mkdir(parents=True, exist_ok=True)

    def translated_status(message: str) -> None:
        status(
            message.replace("dla AMD", "dla DirectML")
            .replace("środowisku AMD", "środowisku DirectML")
            .replace("składnika AMD", "składnika DirectML")
        )

    if not _embedded_python_core_ready(python_path) or not _embedded_pip_ready(python_path):
        status("Przygotowywanie prywatnego Pythona 3.12 dla Whisper DirectML…")
        _install_embedded_python(runtime_dir, translated_status)

    status("Instalowanie PyTorch DirectML i zależności Whispera…")
    _run_install_command(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"torch-directml=={TORCH_DIRECTML_VERSION}",
            "numpy<2",
            "numba>=0.58,<1",
            "tqdm>=4.65,<5",
            "more-itertools>=10,<11",
            "tiktoken>=0.7,<1",
            "ffmpeg-python>=0.2,<1",
        ],
        translated_status,
        "Nie udało się zainstalować środowiska Whisper DirectML.",
    )
    _install_microsoft_whisper_sample(runtime_dir, status)
    _write_worker_script(runtime_dir)
    _write_manifest()
    if not _directml_runtime_ready(python_path):
        raise WhisperDirectMLError(
            "DirectML został zainstalowany, ale test GPU nie przeszedł. "
            "Zaktualizuj sterownik karty graficznej i spróbuj ponownie."
        )
    status("Whisper DirectML jest gotowy do pracy na GPU.")
    return python_path


def _install_microsoft_whisper_sample(runtime_dir: Path, status: Any) -> None:
    downloads = runtime_dir.parent / "directml-runtime-downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive_path = downloads / f"DirectML-{DIRECTML_SAMPLE_COMMIT}.zip"
    if not archive_path.is_file():
        status("Pobieranie oficjalnej wersji Whisper DirectML od Microsoftu…")
        temporary = archive_path.with_suffix(".zip.part")
        try:
            import requests

            with requests.get(DIRECTML_SAMPLE_ARCHIVE, stream=True, timeout=(20, 240)) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            output.write(block)
            temporary.replace(archive_path)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise WhisperDirectMLError(
                f"Nie udało się pobrać oficjalnego sample Whisper DirectML: {exc}"
            ) from exc

    site_packages = runtime_dir / "Lib" / "site-packages"
    target = site_packages / "whisper"
    staging = runtime_dir / ".whisper-directml-staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    marker = "/PyTorch/audio/whisper/whisper/"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            extracted = 0
            for member in archive.infolist():
                normalized = member.filename.replace("\\", "/")
                if marker not in normalized or member.is_dir():
                    continue
                relative = normalized.split(marker, 1)[1]
                if not relative or ".." in Path(relative).parts:
                    continue
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted += 1
            license_member = next(
                (
                    member
                    for member in archive.infolist()
                    if member.filename.replace("\\", "/").endswith(
                        "/PyTorch/audio/whisper/LICENSE"
                    )
                ),
                None,
            )
            if license_member is not None:
                with archive.open(license_member) as source:
                    license_path = runtime_dir / "MICROSOFT_WHISPER_SAMPLE_LICENSE.txt"
                    license_path.write_bytes(source.read())
        if extracted < 8 or not (staging / "__init__.py").is_file():
            raise WhisperDirectMLError("Archiwum Microsoftu nie zawiera kompletnego Whispera.")
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        message = f"Nie udało się przygotować kodu Whisper DirectML: {exc}"
        raise WhisperDirectMLError(message) from exc


def _directml_runtime_ready(python_path: Path) -> bool:
    if not python_path.is_file():
        return False
    code = (
        "import torch,torch_directml,whisper;"
        "assert torch_directml.device_count()>0;"
        "d=torch_directml.device(torch_directml.default_device());"
        "x=torch.tensor([1.0,2.0]).to(d);"
        "y=(x*x).to('cpu');"
        "assert float(y.sum())==5.0;"
        "assert 'large-v3' in whisper.available_models()"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", code],
            check=False,
            capture_output=True,
            timeout=45,
            env=_directml_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _manifest_path() -> Path:
    return directml_runtime_directory() / "polysub-whisper-directml.json"


def _manifest_matches() -> bool:
    try:
        payload = json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("schema") == DIRECTML_RUNTIME_SCHEMA
        and payload.get("torch_directml") == TORCH_DIRECTML_VERSION
        and payload.get("sample_commit") == DIRECTML_SAMPLE_COMMIT
    )


def _write_manifest() -> None:
    _manifest_path().write_text(
        json.dumps(
            {
                "schema": DIRECTML_RUNTIME_SCHEMA,
                "torch_directml": TORCH_DIRECTML_VERSION,
                "sample_commit": DIRECTML_SAMPLE_COMMIT,
                "python": "3.12",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _worker_script_path() -> Path:
    return directml_runtime_directory() / "polysub_whisper_directml_worker.py"


def _write_worker_script(runtime_dir: Path) -> None:
    path = runtime_dir / "polysub_whisper_directml_worker.py"
    path.write_text(_WORKER_SOURCE, encoding="utf-8")


def _run_directml_worker(
    python_path: Path,
    wav_path: Path,
    *,
    model_alias: str,
    device_index: int,
    device_name: str,
) -> dict[str, Any]:
    command = [
        str(python_path),
        str(_worker_script_path()),
        "--audio",
        str(wav_path),
        "--model",
        model_alias,
        "--model-cache",
        str(directml_model_cache()),
        "--device-index",
        str(max(device_index, 0)),
        "--device-name",
        device_name,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=None,
            env=_directml_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise WhisperDirectMLError(f"Nie udało się uruchomić workera DirectML: {exc}") from exc

    payload = _last_json_object(completed.stdout)
    if completed.returncode != 0 or payload is None:
        detail = (completed.stderr or completed.stdout or "")[-1800:]
        raise WhisperDirectMLError(f"Worker DirectML zakończył się błędem. {detail}")
    return payload


def _last_json_object(output: str) -> dict[str, Any] | None:
    for line in reversed((output or "").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _directml_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
    return environment


_WORKER_SOURCE = r'''from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import wave
from pathlib import Path

import numpy as np
import torch
import torch_directml
import whisper


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _choose_device(requested_index: int, requested_name: str):
    count = max(int(torch_directml.device_count()), 0)
    if count <= 0:
        raise RuntimeError("torch-directml nie wykrył żadnej karty DirectX 12")
    names = []
    for index in range(count):
        try:
            names.append(str(torch_directml.device_name(index)))
        except Exception:
            names.append(f"DirectML GPU {index}")
    selected = min(max(requested_index, 0), count - 1)
    wanted = _normalize(requested_name)
    if wanted:
        for index, name in enumerate(names):
            current = _normalize(name)
            if current == wanted or current in wanted or wanted in current:
                selected = index
                break
    return torch_directml.device(selected), selected, names[selected], names


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getframerate() != 16000:
            raise RuntimeError("audio wejściowe DirectML musi być mono PCM 16 kHz")
        width = source.getsampwidth()
        frames = source.readframes(source.getnframes())
    if width != 2:
        raise RuntimeError("audio wejściowe DirectML musi mieć 16-bit PCM")
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _serialize(result: dict) -> list[dict]:
    segments = []
    for segment in result.get("segments") or []:
        words = []
        for word in segment.get("words") or []:
            words.append(
                {
                    "start": float(word.get("start") or 0.0),
                    "end": float(word.get("end") or 0.0),
                    "word": str(word.get("word") or ""),
                }
            )
        segments.append(
            {
                "start": float(segment.get("start") or 0.0),
                "end": float(segment.get("end") or 0.0),
                "text": str(segment.get("text") or ""),
                "words": words,
            }
        )
    return segments


def _transcribe(model, audio: np.ndarray):
    attempts = (
        (True, True, "FP16 + znaczniki słów"),
        (True, False, "FP16 + znaczniki segmentów"),
        (False, False, "FP32 + znaczniki segmentów"),
    )
    failures = []
    for fp16, words, label in attempts:
        try:
            result = model.transcribe(
                audio,
                task="transcribe",
                beam_size=5,
                patience=1.1,
                word_timestamps=words,
                condition_on_previous_text=True,
                temperature=0.0,
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
                fp16=fp16,
                verbose=False,
            )
            degraded = None if not failures else failures[-1]
            return result, label, degraded
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(failures)[-2400:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-cache", required=True)
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--device-name", default="")
    args = parser.parse_args()
    try:
        device, index, name, names = _choose_device(args.device_index, args.device_name)
        # The Microsoft DirectML Whisper fork supplies the DirectML attention path
        # used by its official sample. Model weights are downloaded once into a
        # PolySub-owned cache and reused on subsequent runs.
        model = whisper.load_model(
            args.model,
            device=device,
            download_root=args.model_cache,
            use_dml_attn=True,
        )
        audio = _read_wav(Path(args.audio))
        result, mode, degraded = _transcribe(model, audio)
        payload = {
            "ok": True,
            "backend": "directml",
            "device_index": index,
            "device_name": name,
            "available_devices": names,
            "model": args.model,
            "mode": mode,
            "degraded_reason": degraded,
            "language": result.get("language"),
            "segments": _serialize(result),
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "backend": "directml",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-3000:],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
'''
