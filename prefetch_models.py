from __future__ import annotations

"""
Prefetch heavy models into cache during Docker build, so container runtime starts ready-to-go.

This script is safe to run multiple times: if models are already cached, it will be fast.
"""

import os
from pathlib import Path


def main() -> None:
    # Make sure cache dirs exist (Docker build usually runs as root; runtime can be different)
    hf_home = Path(os.getenv("HF_HOME", "/app/.cache/huggingface")).resolve()
    tts_home = Path(os.getenv("TTS_HOME", "/app/.tts_cache")).resolve()
    hf_home.mkdir(parents=True, exist_ok=True)
    tts_home.mkdir(parents=True, exist_ok=True)

    # Prefetch XTTS (Coqui TTS)
    from tts_engine import TTSEngine

    model_name = os.getenv("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2").strip() or "tts_models/multilingual/multi-dataset/xtts_v2"
    tts = TTSEngine(model_name=model_name)
    # Trigger download/model load
    tts._get_tts()  # noqa: SLF001 (intentional for prefetch)
    print(f"Prefetched TTS model: {model_name}")

    # Optional: prefetch Whisper model weights (helps first ASR request)
    try:
        from faster_whisper import WhisperModel

        whisper_model = os.getenv("WHISPER_MODEL", "small").strip() or "small"
        _ = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        print(f"Prefetched Whisper model: {whisper_model}")
    except Exception as e:
        # Not fatal for TTS readiness
        print(f"Skipping Whisper prefetch (non-fatal): {e}")


if __name__ == "__main__":
    main()

