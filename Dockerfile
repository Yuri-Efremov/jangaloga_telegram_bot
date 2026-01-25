# Dockerfile for Jangaloga Telegram Bot
# Multi-stage build для уменьшения размера образа (опционально)

FROM python:3.10-slim

# Устанавливаем системные зависимости: ffmpeg и необходимые для компиляции C-расширений (если понадобятся)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем requirements и устанавливаем Python-зависимости (сначала базовые, потом TTS)
# Это позволяет кэшировать слои Docker эффективнее
COPY requirements.txt requirements.tts.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements.tts.txt

# Копируем код проекта
COPY *.py ./
COPY dictionary_seed.json jg_generator.py ./

# Копируем готовые файлы из корня
COPY dictionary.json speaker.wav ./

# Создаём директории для временных файлов и кэшей моделей с правами на запись
RUN mkdir -p /app/tmp /app/.cache/huggingface /app/.tts_cache && \
    chmod -R 777 /app/.cache /app/.tts_cache /app/tmp 2>/dev/null || true

# Переменные окружения для Coqui TTS и Hugging Face кэшей
ENV TTS_HOME=/app/.tts_cache
ENV COQUI_TOS_AGREED=1
# Используем HF_HOME (TRANSFORMERS_CACHE устарел в transformers v5+)
ENV HF_HOME=/app/.cache/huggingface

# Предзагрузка моделей в слои образа (чтобы на рантайме не скачивать 1.9+ ГБ)
RUN python prefetch_models.py

# Healthcheck HTTP port (for container platform readiness probes)
EXPOSE 8080

# По умолчанию запускаем бота
CMD ["python", "bot.py"]
