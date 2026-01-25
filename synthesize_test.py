from __future__ import annotations

import argparse
import re
from pathlib import Path

from tts_engine import TTSEngine
from utils import ensure_dir, run_ffmpeg_convert, temp_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick local test for XTTS voice cloning.")
    parser.add_argument("--text", default="монони", help="Text to synthesize (Jangaloga).")
    parser.add_argument("--speaker", default="speaker.wav", help="Reference speaker wav path.")
    parser.add_argument("--out", default="test.wav", help="Output wav path.")
    parser.add_argument("--ogg", action="store_true", help="Also write Telegram-friendly .ogg next to output.")
    parser.add_argument("--tempo", default="0.67", help="ffmpeg atempo (1.0=normal, 0.67≈1.5x slower).")
    args = parser.parse_args()

    speaker = Path(args.speaker)
    out_wav = Path(args.out)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    if not speaker.exists():
        raise SystemExit(f"Speaker wav not found: {speaker}")

    tts = TTSEngine()

    # synth is async under the hood
    import asyncio

    raw_wav = temp_file(".wav")
    asyncio.run(tts.synthesize_to_wav(args.text, speaker_wav=speaker, out_wav=raw_wav))

    try:
        tempo = float(str(args.tempo).strip())
    except ValueError:
        raise SystemExit(f"Bad --tempo: {args.tempo}")
    if not (0.5 <= tempo <= 2.0):
        raise SystemExit("--tempo must be in 0.5..2.0")

    # Apply tempo and write final wav
    if abs(tempo - 1.0) < 1e-6:
        out_wav.write_bytes(raw_wav.read_bytes())
    else:
        asyncio.run(
            run_ffmpeg_convert(
                raw_wav,
                out_wav,
                output_args=["-filter:a", f"atempo={tempo}", "-c:a", "pcm_s16le"],
            )
        )
    print(f"Wrote WAV: {out_wav}")

    if args.ogg:
        out_ogg = out_wav.with_suffix(".ogg")
        ensure_dir(out_ogg.parent)
        asyncio.run(
            run_ffmpeg_convert(
                out_wav,
                out_ogg,
                output_args=["-c:a", "libopus", "-b:a", "48k", "-vbr", "on"],
            )
        )
        print(f"Wrote OGG: {out_ogg}")

    try:
        raw_wav.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()


