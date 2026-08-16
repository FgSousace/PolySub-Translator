from __future__ import annotations

import argparse
import gc
import inspect
import json
import os
import sys
import traceback
import wave
from pathlib import Path

V3_T3_FILENAME = "t3_mtl23ls_v3.safetensors"


def _reply(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _save_pcm(path: Path, audio, sample_rate: int) -> None:
    samples = audio.detach().cpu().squeeze().clamp(-1.0, 1.0)
    pcm = (samples * 32767).to(dtype=__import__("torch").int16).numpy().tobytes()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)


def _use_local_chatterbox_assets(model_dir: Path, tokenizer_module=None) -> None:
    """Keep Chatterbox's tokenizer inside the already managed V3 snapshot."""

    if tokenizer_module is None:
        import chatterbox.models.tokenizers.tokenizer as tokenizer_module

    def local_asset(*_args, filename=None, **_kwargs):
        if filename is None and len(_args) > 1:
            filename = _args[1]
        candidate = model_dir / str(filename or "")
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"Missing local Chatterbox asset: {candidate.name}")

    # The upstream tokenizer initializes its Chinese converter for every language
    # and otherwise calls hf_hub_download for Cangjie5_TC.json. PolySub already
    # downloads that exact file, so return it directly and avoid a hidden network
    # request or a second nested cache while synthesizing Polish speech.
    tokenizer_module.hf_hub_download = local_asset


def _load_chatterbox_multilingual_v3(model_dir: Path, device: str, mtl_module=None):
    """Load V3 with both the released 0.1.7 wheel and the current upstream API."""

    model_dir = Path(model_dir)
    checkpoint = model_dir / V3_T3_FILENAME
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Missing local Chatterbox V3 checkpoint: {checkpoint}")

    if mtl_module is None:
        import chatterbox.mtl_tts as mtl_module

    model_class = mtl_module.ChatterboxMultilingualTTS
    parameters = inspect.signature(model_class.from_local).parameters
    if "t3_model" in parameters:
        return model_class.from_local(model_dir, device=device, t3_model="v3")

    # The published chatterbox-tts 0.1.7 wheel predates V3 support and hardcodes
    # t3_mtl23ls_v2.safetensors. Mirror the upstream from_local implementation
    # while selecting the already downloaded V3 checkpoint. This avoids copying
    # the multi-gigabyte weights or mutating Hugging Face's snapshot directory.
    torch_module = mtl_module.torch
    map_location = torch_module.device("cpu") if device in {"cpu", "mps"} else None

    voice_encoder = mtl_module.VoiceEncoder()
    voice_encoder.load_state_dict(
        torch_module.load(
            model_dir / "ve.pt",
            map_location=map_location,
            weights_only=True,
        )
    )
    voice_encoder.to(device).eval()

    t3 = mtl_module.T3(mtl_module.T3Config.multilingual())
    t3_state = mtl_module.load_safetensors(checkpoint)
    if "model" in t3_state:
        t3_state = t3_state["model"][0]
    t3.load_state_dict(t3_state)
    t3.to(device).eval()

    s3gen = mtl_module.S3Gen()
    s3gen.load_state_dict(
        torch_module.load(
            model_dir / "s3gen.pt",
            map_location=map_location,
            weights_only=True,
        )
    )
    s3gen.to(device).eval()

    tokenizer = mtl_module.MTLTokenizer(
        str(model_dir / "grapheme_mtl_merged_expanded_v1.json")
    )
    conditionals = None
    builtin_voice = model_dir / "conds.pt"
    if builtin_voice.exists():
        conditionals = mtl_module.Conditionals.load(
            builtin_voice,
            map_location=map_location,
        ).to(device)

    return model_class(
        t3,
        s3gen,
        voice_encoder,
        tokenizer,
        device,
        conds=conditionals,
    )


def _clear_accelerator_cache(torch_module) -> None:
    try:
        if torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()


def _load_with_device_fallback(
    model_dir: Path,
    requested_device: str,
    *,
    loader=_load_chatterbox_multilingual_v3,
    torch_module=None,
):
    requested = str(requested_device or "cpu")
    try:
        return loader(model_dir, device=requested), requested, None
    except Exception as exc:
        if requested == "cpu":
            raise
        if torch_module is None:
            import torch as torch_module
        _clear_accelerator_cache(torch_module)
        fallback_model = loader(model_dir, device="cpu")
        return fallback_model, "cpu", str(exc)


def _generate_with_device_fallback(
    model,
    model_dir: Path,
    active_device: str,
    *,
    text: str,
    language_id: str,
    exaggeration: float,
    cfg_weight: float,
):
    try:
        audio = model.generate(
            text,
            language_id=language_id,
            audio_prompt_path=None,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        return model, active_device, audio, None
    except Exception as exc:
        if active_device == "cpu":
            raise
        import torch

        del model
        _clear_accelerator_cache(torch)
        cpu_model = _load_chatterbox_multilingual_v3(model_dir, device="cpu")
        audio = cpu_model.generate(
            text,
            language_id=language_id,
            audio_prompt_path=None,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        return cpu_model, "cpu", audio, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--language", default="pl")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--device",
        default=os.getenv("POLYSUB_NARRATOR_DEVICE", "cpu"),
    )
    args = parser.parse_args()
    try:
        import torch

        torch.set_num_threads(max(args.threads, 1))
        torch.set_num_interop_threads(1)
        _use_local_chatterbox_assets(args.model_dir)

        requested_device = str(args.device or "cpu")
        model, active_device, load_fallback = _load_with_device_fallback(
            args.model_dir,
            requested_device,
            torch_module=torch,
        )
        sample_rate = int(model.sr)
        _reply(
            {
                "ready": True,
                "sample_rate": sample_rate,
                "device": active_device,
                "requested_device": requested_device,
                "backend": os.getenv("POLYSUB_NARRATOR_BACKEND", "cpu"),
                "fallback": load_fallback,
            }
        )
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("command") == "close":
                    _reply({"closed": True})
                    return 0
                output = Path(str(request["output"]))
                output.parent.mkdir(parents=True, exist_ok=True)
                model, active_device, audio, generation_fallback = (
                    _generate_with_device_fallback(
                        model,
                        args.model_dir,
                        active_device,
                        text=str(request["text"]),
                        language_id=str(request.get("language") or args.language),
                        exaggeration=float(request.get("exaggeration", 0.45)),
                        cfg_weight=float(request.get("cfg_weight", 0.5)),
                    )
                )
                _save_pcm(output, audio, sample_rate)
                _reply(
                    {
                        "ok": True,
                        "output": str(output),
                        "sample_rate": sample_rate,
                        "device": active_device,
                        "fallback": generation_fallback,
                    }
                )
            except Exception as exc:
                _reply({"ok": False, "error": str(exc), "device": active_device})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
