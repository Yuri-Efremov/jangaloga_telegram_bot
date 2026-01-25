from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TTSEngine:
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    language: str = "ru"

    def __post_init__(self) -> None:
        self._tts: object | None = None

    def _get_tts(self):
        if self._tts is None:
            try:
                tts_api = importlib.import_module("TTS.api")
                TTS = getattr(tts_api, "TTS")
            except Exception as e:
                raise RuntimeError(
                    "Пакет 'TTS' не установлен. Для синтеза установите зависимости:\n"
                    "  pip install -r requirements.tts.txt\n\n"
                    "На Windows может потребоваться Microsoft C++ Build Tools (MSVC 14+)."
                ) from e
            self._tts = TTS(self.model_name)
        return self._tts

    async def synthesize_to_wav(self, text: str, speaker_wav: Path, out_wav: Path) -> None:
        """
        XTTS voice cloning: speaker_wav is your reference voice sample (wav).
        """
        tts = self._get_tts()

        def _run() -> None:
            tts.tts_to_file(
                text=text,
                file_path=str(out_wav),
                speaker_wav=str(speaker_wav),
                language=self.language,
            )

        await asyncio.to_thread(_run)


