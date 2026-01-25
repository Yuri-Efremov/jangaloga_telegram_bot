from __future__ import annotations

import asyncio
import os
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import FSInputFile
from dotenv import load_dotenv
from aiohttp import web

from asr import ASR
from translator import Dictionary
from tts_engine import TTSEngine
from utils import ensure_dir, run_ffmpeg_convert, temp_file

logger = logging.getLogger("jangaloga_bot")


@dataclass
class AppConfig:
    bot_token: str
    data_dir: Path
    dict_path: Path
    speaker_wav: Path
    # ffmpeg atempo: 1.0 = normal, 0.67 ~ 1.5x slower
    speech_tempo: float = 0.67
    # Telegram request timeout for uploads (seconds)
    telegram_timeout: float = 180.0
    # Input limits
    max_text_chars: int = 400
    max_voice_seconds: int = 45
    # Healthcheck HTTP server (for container platforms readiness/liveness probes)
    health_port: int = 8080
    whisper_model: str = "small"
    tts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    tts_language: str = "ru"

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()  # reads .env if present
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Не задан BOT_TOKEN (см. env.example).")
        # Временная папка для скачанных voice-файлов (опционально, можно использовать системный temp)
        data_dir_raw = os.getenv("DATA_DIR", "./tmp").strip()
        data_dir = Path(data_dir_raw).resolve()
        # Словарь и референс-голос теперь в корне проекта
        dict_path = Path(os.getenv("DICT_PATH", "./dictionary.json")).resolve()
        speaker_wav = Path(os.getenv("SPEAKER_WAV", "./speaker.wav")).resolve()
        speech_tempo_raw = os.getenv("SPEECH_TEMPO", "0.67").strip() or "0.67"
        try:
            speech_tempo = float(speech_tempo_raw)
        except ValueError as e:
            raise RuntimeError(f"Некорректный SPEECH_TEMPO: {speech_tempo_raw}") from e
        if not (0.5 <= speech_tempo <= 2.0):
            raise RuntimeError("SPEECH_TEMPO должен быть в диапазоне 0.5..2.0 (ffmpeg atempo).")

        telegram_timeout_raw = os.getenv("TELEGRAM_TIMEOUT", "180").strip() or "180"
        try:
            telegram_timeout = float(telegram_timeout_raw)
        except ValueError as e:
            raise RuntimeError(f"Некорректный TELEGRAM_TIMEOUT: {telegram_timeout_raw}") from e
        if telegram_timeout < 30:
            raise RuntimeError("TELEGRAM_TIMEOUT должен быть >= 30 секунд.")

        max_text_chars_raw = os.getenv("MAX_TEXT_CHARS", "400").strip() or "400"
        try:
            max_text_chars = int(max_text_chars_raw)
        except ValueError as e:
            raise RuntimeError(f"Некорректный MAX_TEXT_CHARS: {max_text_chars_raw}") from e
        if max_text_chars < 50:
            raise RuntimeError("MAX_TEXT_CHARS должен быть >= 50.")

        max_voice_seconds_raw = os.getenv("MAX_VOICE_SECONDS", "45").strip() or "45"
        try:
            max_voice_seconds = int(max_voice_seconds_raw)
        except ValueError as e:
            raise RuntimeError(f"Некорректный MAX_VOICE_SECONDS: {max_voice_seconds_raw}") from e
        if max_voice_seconds < 5:
            raise RuntimeError("MAX_VOICE_SECONDS должен быть >= 5.")

        # Cloud container platforms often provide PORT env var for readiness probe
        health_port_raw = os.getenv("PORT", os.getenv("HEALTH_PORT", "8080")).strip() or "8080"
        try:
            health_port = int(health_port_raw)
        except ValueError as e:
            raise RuntimeError(f"Некорректный PORT/HEALTH_PORT: {health_port_raw}") from e
        if not (1 <= health_port <= 65535):
            raise RuntimeError("PORT/HEALTH_PORT должен быть в диапазоне 1..65535.")
        return cls(
            bot_token=token,
            data_dir=data_dir,
            dict_path=dict_path,
            speaker_wav=speaker_wav,
            speech_tempo=speech_tempo,
            telegram_timeout=telegram_timeout,
            max_text_chars=max_text_chars,
            max_voice_seconds=max_voice_seconds,
            health_port=health_port,
            whisper_model=os.getenv("WHISPER_MODEL", "small").strip() or "small",
            tts_model=os.getenv("TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2").strip()
            or "tts_models/multilingual/multi-dataset/xtts_v2",
            tts_language=os.getenv("TTS_LANGUAGE", "ru").strip() or "ru",
        )


router = Router()
_HAS_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+", flags=re.UNICODE)
PROCESS_LOCK = asyncio.Lock()

async def _start_health_server(port: int) -> web.AppRunner:
    """
    Minimal HTTP server for container readiness/liveness probes.
    Responds 200 on '/' and '/healthz'.
    """
    app = web.Application()

    async def _ok(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/", _ok)
    app.router.add_get("/healthz", _ok)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner

@router.message(Command("start", "help"))
async def cmd_help(message: types.Message) -> None:
    text = (
        "Привет, друг, или как говорят у нас: 'Монони губожя'. Я гунажий бот для перевода твоего текста (или голосовухи) с русского на мой язык Джангалогу.\n\n"
        "Отправь voice или текст — и получи перевод + озвучку."
    )
    await message.answer(text)


async def _speak_and_send(
    message: types.Message,
    *,
    tts: TTSEngine,
    speaker_wav: Path,
    jg_text: str,
    speech_tempo: float,
    telegram_timeout: float,
) -> None:
    out_wav = temp_file(".wav")
    slowed_wav: Path | None = None
    out_ogg: Path | None = None
    status = await message.answer("Озвучиваю…")
    try:
        logger.info("TTS start")
        await tts.synthesize_to_wav(jg_text, speaker_wav=speaker_wav, out_wav=out_wav)
        logger.info("TTS done: %s", out_wav)

        # Slow down for readability (without pitch change) via ffmpeg atempo
        if abs(speech_tempo - 1.0) > 1e-6:
            slowed_wav = temp_file(".wav")
            logger.info("Applying tempo=%s", speech_tempo)
            await run_ffmpeg_convert(
                out_wav,
                slowed_wav,
                output_args=["-filter:a", f"atempo={speech_tempo}", "-c:a", "pcm_s16le"],
            )
            wav_for_ogg = slowed_wav
        else:
            wav_for_ogg = out_wav

        out_ogg = temp_file(".ogg")
        logger.info("Encoding opus ogg")
        await run_ffmpeg_convert(
            wav_for_ogg,
            out_ogg,
            # Smaller + more "voice-note" oriented opus settings to reduce upload timeouts
            output_args=["-ac", "1", "-c:a", "libopus", "-b:a", "24k", "-vbr", "on", "-application", "voip"],
        )
        try:
            size = out_ogg.stat().st_size
        except Exception:
            size = -1
        logger.info("OGG ready: %s bytes=%s", out_ogg, size)
        await status.delete()
        voice_file = FSInputFile(str(out_ogg))
        # Retry on transient network timeouts (WinError 121)
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                logger.info("Sending voice attempt=%s timeout=%s", attempt + 1, telegram_timeout)
                await message.answer_voice(voice=voice_file, request_timeout=telegram_timeout)
                last_exc = None
                logger.info("Voice sent")
                break
            except TelegramNetworkError as e:
                last_exc = e
                logger.warning("Voice send failed attempt=%s: %s", attempt + 1, e)
                await asyncio.sleep(2 * (attempt + 1))
        if last_exc is not None:
            # Fallback: try to send as regular audio (sometimes more tolerant)
            logger.warning("Falling back to send_audio")
            for attempt in range(2):
                try:
                    await message.answer_audio(audio=voice_file, request_timeout=telegram_timeout)
                    last_exc = None
                    logger.info("Audio sent")
                    break
                except TelegramNetworkError as e:
                    last_exc = e
                    logger.warning("Audio send failed attempt=%s: %s", attempt + 1, e)
                    await asyncio.sleep(2 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
    finally:
        for p in [out_wav, slowed_wav, out_ogg]:
            if p is None:
                continue
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


@router.message(F.voice)
async def on_voice(
    message: types.Message,
    bot: Bot,
    cfg: AppConfig,
    asr: ASR,
    dictionary: Dictionary,
    tts: TTSEngine,
) -> None:
    if message.from_user is None or message.voice is None:
        return

    data_dir = ensure_dir(cfg.data_dir)
    tmp_dir = ensure_dir(data_dir / "tmp")
    if not cfg.speaker_wav.exists():
        await message.answer(f"Не найден SPEAKER_WAV: {cfg.speaker_wav}. Добавьте референс-голос (wav) и перезапустите бота.")
        return

    # Download Telegram voice (ogg/opus)
    voice = message.voice
    if voice.duration is not None and voice.duration > cfg.max_voice_seconds:
        await message.answer(
            f"Сообщение слишком длинное для обработки: {voice.duration} сек.\n"
            f"Пожалуйста, сократите до {cfg.max_voice_seconds} сек или меньше."
        )
        return

    if PROCESS_LOCK.locked():
        await message.answer("Сейчас обрабатываю другое сообщение. Пожалуйста, попробуйте ещё раз через минуту.")
        return

    async with PROCESS_LOCK:
        ogg_in = tmp_dir / f"in_{voice.file_unique_id}.ogg"
        file = await bot.get_file(voice.file_id)
        await bot.download_file(file.file_path, destination=ogg_in)

        # Convert to wav for ASR / speaker ref
        wav = tmp_dir / f"in_{voice.file_unique_id}.wav"
        await run_ffmpeg_convert(
            ogg_in,
            wav,
            output_args=["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le"],
        )

        status = await message.answer("Слышу. Распознаю речь…")

        # ASR (Russian)
        ru_text = await asr.transcribe_ru(wav)
        if not ru_text:
            await status.edit_text("Не удалось распознать речь. Попробуй говорить чуть громче/чище.")
            return
        if len(ru_text) > cfg.max_text_chars:
            await status.delete()
            await message.answer(
                f"Распознанный текст слишком длинный для обработки ({len(ru_text)} символов).\n"
                f"Пожалуйста, сократите сообщение до {cfg.max_text_chars} символов или меньше."
            )
            return

        await status.edit_text("Перевожу по словарю…")
        jg_text = dictionary.translate_text(ru_text)
        if not _HAS_WORD_RE.search(jg_text):
            await status.delete()
            await message.answer(
                "Не получилось перевести на Джангалогу: в распознанном тексте не нашлось слов из словаря.\n"
                "Попробуйте переформулировать."
            )
            return

        try:
            await status.delete()
            await message.answer(jg_text)
            try:
                await _speak_and_send(
                    message,
                    tts=tts,
                    speaker_wav=cfg.speaker_wav,
                    jg_text=jg_text,
                    speech_tempo=cfg.speech_tempo,
                    telegram_timeout=cfg.telegram_timeout,
                )
            except Exception:
                logger.exception("TTS/send failed (voice)")
                await message.answer(
                    "Перевод готов, но озвучку отправить не удалось (ошибка синтеза или загрузки voice в Telegram).\n"
                    "Попробуйте ещё раз чуть позже."
                )
        finally:
            # Best-effort cleanup
            for p in [ogg_in, wav]:
                if p is None:
                    continue
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass


@router.message(F.text)
async def on_text(message: types.Message, cfg: AppConfig, dictionary: Dictionary, tts: TTSEngine) -> None:
    if message.text is None:
        return
    if message.text.strip().startswith("/"):
        return
    if not cfg.speaker_wav.exists():
        await message.answer(f"Не найден SPEAKER_WAV: {cfg.speaker_wav}. Добавьте референс-голос (wav) и перезапустите бота.")
        return

    ru_text = message.text.strip()
    if len(ru_text) > cfg.max_text_chars:
        await message.answer(
            f"Текст слишком длинный для обработки ({len(ru_text)} символов).\n"
            f"Пожалуйста, сократите до {cfg.max_text_chars} символов или меньше."
        )
        return
    jg_text = dictionary.translate_text(ru_text)
    if not _HAS_WORD_RE.search(jg_text):
        await message.answer(
            "Не получилось перевести на Джангалогу: в тексте не нашлось слов из словаря.\n"
            "Попробуйте переформулировать."
        )
        return

    if PROCESS_LOCK.locked():
        await message.answer(jg_text + "\n\n(Озвучка: бот сейчас занят другим сообщением, попробуйте ещё раз через минуту.)")
        return
    async with PROCESS_LOCK:
        await message.answer(jg_text)
        try:
            await _speak_and_send(
                message,
                tts=tts,
                speaker_wav=cfg.speaker_wav,
                jg_text=jg_text,
                speech_tempo=cfg.speech_tempo,
                telegram_timeout=cfg.telegram_timeout,
            )
        except Exception:
            logger.exception("TTS/send failed (text)")
            await message.answer(
                "Перевод готов, но озвучку отправить не удалось (ошибка синтеза или загрузки voice в Telegram).\n"
                "Попробуйте ещё раз чуть позже."
            )


async def main() -> None:
    # Ensure logs are visible in container logs (Cloud.ru)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

    cfg = AppConfig.from_env()
    dp = Dispatcher()
    dp.include_router(router)

    data_dir = ensure_dir(cfg.data_dir)
    dictionary = Dictionary.load(cfg.dict_path)
    if not cfg.dict_path.exists():
        raise RuntimeError(
            f"Словарь не найден: {cfg.dict_path}. "
            f"Сначала запустите: python build_dictionary.py --out \"{cfg.dict_path}\""
        )

    # Use a longer aiohttp timeout for polling/network operations (seconds)
    # Note: aiogram expects `session.timeout` to be a number (not aiohttp.ClientTimeout).
    session = AiohttpSession(timeout=cfg.telegram_timeout)
    bot = Bot(token=cfg.bot_token, session=session)

    # If this bot previously used a webhook (or another platform set it),
    # polling will fail with TelegramConflictError until webhook is deleted.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    asr = ASR(model_name=cfg.whisper_model)
    tts = TTSEngine(model_name=cfg.tts_model, language=cfg.tts_language)

    # Dependency injection for handlers
    dp["cfg"] = cfg
    dp["asr"] = asr
    dp["dictionary"] = dictionary
    dp["tts"] = tts

    # Start health server for container platform probes
    health_runner: web.AppRunner | None = None
    try:
        health_runner = await _start_health_server(cfg.health_port)
        await dp.start_polling(bot)
    finally:
        if health_runner is not None:
            try:
                await health_runner.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())


