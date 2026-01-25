from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg не найден в PATH. Установите ffmpeg и добавьте его в PATH "
            "(нужно для конвертации Telegram voice/ogg)."
        )


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name.strip("._-") or "file"


async def run_ffmpeg_convert(input_path: Path, output_path: Path, output_args: list[str]) -> None:
    """
    Runs: ffmpeg -y -i <input> <output_args...> <output>
    """
    ensure_ffmpeg_available()
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path)]
    cmd.extend(output_args)
    cmd.append(str(output_path))

    def _run() -> None:
        subprocess.run(cmd, check=True)

    await asyncio.to_thread(_run)


def temp_file(suffix: str) -> Path:
    fd, p = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(p)


