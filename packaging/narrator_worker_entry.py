from __future__ import annotations

import argparse
import json
import sys
import traceback
import wave
from pathlib import Path


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
    # and otherwise calls hf_hub_download for Cangjie5_TC.json.  PolySub already
    # downloads that exact file, so return it directly and avoid a hidden network
    # request or a second nested cache while synthesizing Polish speech.
    tokenizer_module.hf_hub_download = local_asset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--language", default="pl")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    try:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        torch.set_num_threads(max(args.threads, 1))
        torch.set_num_interop_threads(1)
        _use_local_chatterbox_assets(args.model_dir)
        model = ChatterboxMultilingualTTS.from_local(
            args.model_dir,
            device="cpu",
            t3_model="v3",
        )
        sample_rate = int(model.sr)
        _reply({"ready": True, "sample_rate": sample_rate})
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("command") == "close":
                    _reply({"closed": True})
                    return 0
                output = Path(str(request["output"]))
                output.parent.mkdir(parents=True, exist_ok=True)
                audio = model.generate(
                    str(request["text"]),
                    language_id=str(request.get("language") or args.language),
                    audio_prompt_path=None,
                    exaggeration=float(request.get("exaggeration", 0.45)),
                    cfg_weight=float(request.get("cfg_weight", 0.5)),
                )
                _save_pcm(output, audio, sample_rate)
                _reply({"ok": True, "output": str(output), "sample_rate": sample_rate})
            except Exception as exc:
                _reply({"ok": False, "error": str(exc)})
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
