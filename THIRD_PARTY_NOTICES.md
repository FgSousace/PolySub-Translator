# Third-party notices

Starting with version 0.4.9, PolySub Translator™ is licensed under the PolyForm Noncommercial
License 1.0.0. The Windows package also contains or uses the following separately licensed
components:

- **faster-whisper** — MIT License — https://github.com/SYSTRAN/faster-whisper
- **CTranslate2** — MIT License — https://github.com/OpenNMT/CTranslate2
- **PyAV** — BSD 3-Clause License — https://github.com/PyAV-Org/PyAV
- **imageio-ffmpeg** — BSD 2-Clause License — https://github.com/imageio/imageio-ffmpeg
- **FFmpeg executable distributed by imageio-ffmpeg** — its exact build configuration and license
  are available by running `ffmpeg -L`. FFmpeg source and license information:
  https://ffmpeg.org/download.html and https://ffmpeg.org/legal.html
- **ONNX Runtime** — MIT License — https://github.com/microsoft/onnxruntime
- **PyTorch** — BSD-style License — https://github.com/pytorch/pytorch
- **Transformers** — Apache License 2.0 — https://github.com/huggingface/transformers
- **Hugging Face Hub client** — Apache License 2.0 — https://github.com/huggingface/huggingface_hub
- **SentencePiece** — Apache License 2.0 — https://github.com/google/sentencepiece
- **NVIDIA CUDA runtime libraries** — NVIDIA CUDA Toolkit End User License Agreement —
  https://docs.nvidia.com/cuda/eula/
- **NVIDIA cuDNN runtime libraries** — NVIDIA cuDNN Software License Agreement —
  https://docs.nvidia.com/deeplearning/cudnn/latest/reference/eula.html
- **AMD ROCm runtime libraries** — optionally downloaded from AMD into an isolated environment;
  AMD ROCm licenses — https://rocm.docs.amd.com/en/latest/about/license.html
- **CPython embedded distribution** — automatically downloaded from python.org only for the
  isolated AMD and Chatterbox workers; Python Software Foundation License —
  https://docs.python.org/3/license.html
- **Chatterbox TTS** — optionally installed in an isolated runtime; MIT License —
  https://github.com/resemble-ai/chatterbox
- **Resemble Perth neural watermarking** — installed with the optional narrator runtime;
  MIT License — https://github.com/resemble-ai/perth
- **libass** (used by FFmpeg for permanent subtitle rendering when present in the bundled build)
  — ISC License — https://github.com/libass/libass

Downloaded speech-recognition and translation model weights remain subject to the licenses shown
on their respective Hugging Face model pages. PolySub does not bundle those model weights in the
installer. The translation catalog currently links to these separately licensed model families:

- **Meta M2M100** — MIT License — https://huggingface.co/facebook/m2m100_418M
- **Meta NLLB-200** — CC-BY-NC-4.0; research/noncommercial use —
  https://huggingface.co/facebook/nllb-200-distilled-600M
- **Meta mBART-50** — terms shown on each model card —
  https://huggingface.co/facebook/mbart-large-50-many-to-many-mmt
- **Helsinki-NLP OPUS-MT models** — Apache License 2.0 —
  https://huggingface.co/Helsinki-NLP/opus-mt-en-zlw
- **SYSTRAN faster-whisper model conversions** — MIT License —
  https://huggingface.co/collections/Systran/faster-whisper
- **Chatterbox Multilingual V3 weights** — MIT License —
  https://huggingface.co/ResembleAI/chatterbox
