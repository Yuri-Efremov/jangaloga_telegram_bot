from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel


@dataclass
class ASR:
    model_name: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"

    def __post_init__(self) -> None:
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    async def transcribe_ru(self, wav_path: Path) -> str:
        """
        Returns plain text transcription in Russian.
        """
        model = self._get_model()

        def _run() -> str:
            segments, _info = model.transcribe(
                str(wav_path),
                language="ru",
                vad_filter=True,
                beam_size=5,
            )
            return "".join(seg.text for seg in segments).strip()

        return await asyncio.to_thread(_run)


