### Jangaloga Telegram Bot (MVP)

Этот бот делает:

- **Telegram voice (RU) → распознавание речи → текст на русском**
- **Перевод в Джангалогу по словарю** (пока словарный/лексический, без “умного” перевода)
- **Озвучка перевода вашим голосом** через **Coqui XTTS v2** (один фиксированный референс-голос `SPEAKER_WAV`)
- **Текстовые сообщения тоже поддерживаются** (RU текст → Джангалога → озвучка)

Важно: я **не предлагаю слова для словаря**, пока вы не попросите.

---

### Что нужно установить (Windows)

1) **Python 3.10–3.11** (рекомендуется 3.10).
   Если при запуске `python` открывается Microsoft Store или команда не находится — установите Python с `python.org` и/или отключите **App execution aliases** для Python в настройках Windows.

2) **ffmpeg** (обязательно): должен быть доступен как команда `ffmpeg` в PATH.

3) Зависимости Python:

```bash
cd jangaloga_telegram_bot
python -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

Синтез речи (`TTS`) устанавливается **отдельно**, потому что на Windows может понадобиться MSVC Build Tools:

```bash
pip install -r requirements.tts.txt
```

Если при синтезе появляется ошибка импорта `BeamSearchScorer` из `transformers`, выполните повторно
`pip install -r requirements.tts.txt` — там закреплена совместимая версия `transformers`.

Если при загрузке XTTS вы видите ошибку `Weights only load failed` (PyTorch 2.6+), выполните
`pip install -r requirements.tts.txt` — там закреплён `torch<2.6`.

---

### Настройка

1) Скопируйте `env.example` в `.env` (создайте файл `.env` рядом с `bot.py`) и заполните:

- `BOT_TOKEN` — токен вашего Telegram-бота
- `SPEAKER_WAV` — путь к вашему референс-голосу (wav)
- `SPEECH_TEMPO` — темп речи (ffmpeg atempo): `1.0` нормально, `0.67` ≈ в 1.5 раза медленнее

2) Сборка словаря (1 раз):

```bash
python build_dictionary.py --n 2500 --out dictionary.json
```

Фиксированные пары берутся из `dictionary_seed.json` и **не перезаписываются**.
В переводе включена **лемматизация русского текста** (чтобы “иду/шёл/пойдём” находились как “идти” в словаре).

3) Запуск:

```bash
python bot.py
```

---

### Быстрая проверка синтеза без Telegram

После того как вы положили `speaker.wav` в корень проекта:

```bash
pip install -r requirements.tts.txt
python synthesize_test.py --text "монони" --speaker speaker.wav --out test.wav
```

---

### Как запустить бота 24/7 бесплатно (когда ваш ПК выключен)

Чтобы бот работал всегда, он должен быть постоянно запущен **на каком-то сервере**.
Вариант с бюджетом **0** и некоммерческим использованием обычно выглядит так:

- **Oracle Cloud “Always Free” VPS** (часто требует привязку банковской карты для верификации, но тариф может быть $0).

Ниже — базовый рецепт под **Ubuntu** на VPS.

#### 1) Подготовьте сервер

- Установите Ubuntu (на Oracle/любом VPS это обычно делается в панели).
- Подключитесь по SSH.

#### 2) Установите зависимости

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg
```

#### 3) Загрузите проект на сервер

Самый простой способ:
- залить код в приватный GitHub репозиторий и сделать `git clone`
- или скопировать папку `jangaloga_telegram_bot` через `scp`

Важно: перенесите также:
- `dictionary.json` (из корня проекта)
- `speaker.wav` (из корня проекта)
- `.env` (с BOT_TOKEN)

#### 4) Установите Python-зависимости

```bash
cd jangaloga_telegram_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -r requirements.tts.txt
```

#### 5) Проверьте локально на сервере

```bash
python synthesize_test.py --text "монони" --speaker speaker.wav --out test.wav
```

#### 6) Сделайте автозапуск (systemd)

Создайте сервис:

```bash
sudo nano /etc/systemd/system/jangaloga-bot.service
```

Вставьте (поправьте пути под вашего пользователя):

```ini
[Unit]
Description=Jangaloga Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/jangaloga_telegram_bot
EnvironmentFile=/home/ubuntu/jangaloga_telegram_bot/.env
ExecStart=/home/ubuntu/jangaloga_telegram_bot/.venv/bin/python /home/ubuntu/jangaloga_telegram_bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jangaloga-bot
sudo systemctl status jangaloga-bot --no-pager
```

Логи:

```bash
journalctl -u jangaloga-bot -f
```


---

### Деплой в контейнере (Cloud.ru, Docker)

Бот готов к запуску в Docker-контейнере. В репозитории есть `Dockerfile` и `.dockerignore`.

#### Подготовка к деплою

1) **Подготовьте файлы** (из корня проекта):
   - `dictionary.json` (обязательно, уже должен быть готов)
   - `speaker.wav` (обязательно)

2) **Переменные окружения** (через Cloud.ru UI/конфиг контейнера):
   - `BOT_TOKEN` — токен Telegram-бота
   - `SPEAKER_WAV=/app/speaker.wav` (по умолчанию)
   - `DICT_PATH=/app/dictionary.json` (по умолчанию)
   - При необходимости: `TELEGRAM_TIMEOUT=300`, `SPEECH_TEMPO=0.67` и т.п.

#### На Cloud.ru (примерный процесс)

1) **Создайте контейнерную среду** (Container/Kubernetes) и укажите:
   - **Image build из `Dockerfile`** (или соберите локально и push в registry Cloud.ru)
   - **Volumes** (опционально): если файлы не в образе, монтируйте `dictionary.json` и `speaker.wav` в `/app/`

2) **Переменные окружения** задайте через панель Cloud.ru (Environment Variables)

3) **Запустите контейнер** — бот автоматически стартует через `CMD ["python", "bot.py"]`

#### Дополнительные замечания

- **Лицензия Coqui TTS**: в `Dockerfile` установлена переменная `COQUI_TOS_AGREED=1`, чтобы избежать интерактивного подтверждения при первом запуске
- **Размер образа**: может быть ~2–3 ГБ из‑за моделей TTS/Whisper (они скачиваются при первом запуске). Это нормально для такого типа ботов
- **Ресурсы**: рекомендую минимум **2 GB RAM** и **2 CPU cores** для стабильной работы XTTS v2

---

### Как пользоваться в Telegram

Отправьте voice или текст — бот вернёт:

- распознанный русский текст
- перевод на Джангалогу (по словарю)
- voice с озвучкой перевода вашим голосом

---

### Словарь

- Seed-словарь: `dictionary_seed.json` (ваши фиксированные соответствия)
- Итоговый словарь, который использует бот: `dictionary.json` (в корне проекта, генерируется `build_dictionary.py`)
- Неизвестные русские слова **удаляются** из перевода (в результате остаются только слова на Джангалоге + пунктуация)

---

### Перевод файла .txt (для подготовки текста на начитку)

1) Положите русский текст в файл, например `ru.txt` (UTF-8).
2) Выполните:

```bash
python translate_file.py --in ru.txt --out jg.txt --dict dictionary.json
```

На выходе получите `jg.txt` — его можно читать/надиктовывать.


