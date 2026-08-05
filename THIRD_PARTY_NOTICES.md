# Third-party notices

PolySub Translator is licensed under the MIT License. The Windows package also contains or uses
the following separately licensed components:

- **faster-whisper** — MIT License — https://github.com/SYSTRAN/faster-whisper
- **CTranslate2** — MIT License — https://github.com/OpenNMT/CTranslate2
- **PyAV** — BSD 3-Clause License — https://github.com/PyAV-Org/PyAV
- **imageio-ffmpeg** — BSD 2-Clause License — https://github.com/imageio/imageio-ffmpeg
- **FFmpeg executable distributed by imageio-ffmpeg** — its exact build configuration and license
  are available by running `ffmpeg -L`. FFmpeg source and license information:
  https://ffmpeg.org/download.html and https://ffmpeg.org/legal.html
- **ONNX Runtime** — MIT License — https://github.com/microsoft/onnxruntime
- **PyTorch** — BSD-style License — https://github.com/pytorch/pytorch
- **NVIDIA CUDA runtime libraries** — NVIDIA CUDA Toolkit End User License Agreement —
  https://docs.nvidia.com/cuda/eula/
- **NVIDIA cuDNN runtime libraries** — NVIDIA cuDNN Software License Agreement —
  https://docs.nvidia.com/deeplearning/cudnn/latest/reference/eula.html
- **libass** (used by FFmpeg for permanent subtitle rendering when present in the bundled build)
  — ISC License — https://github.com/libass/libass

Downloaded speech-recognition and translation model weights remain subject to the licenses shown
on their respective Hugging Face model pages. PolySub does not bundle those model weights in the
installer.
