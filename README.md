<div align="center">

# MashMachine
### Neural Voice Conversion & Music Mashup Pipeline

Автоматизированный пайплайн для создания каверов и мешапов в Telegram.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram 3.16+](https://img.shields.io/badge/Aiogram-3.16%2B-2CA5E0?style=flat-square)](https://docs.aiogram.dev/)
[![RVC Engine](https://img.shields.io/badge/RVC-Applio_v3.6.5-orange?style=flat-square)](https://github.com/IAHispano/Applio)
[![Demucs v4](https://img.shields.io/badge/Audio_Separation-Demucs_v4-7B1FA2?style=flat-square)](https://github.com/facebookresearch/demucs)
[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA_12.1-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)](https://pytorch.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Ключевые возможности

| Функция | Описание |
| :--- | :--- |
| **Стем-сплиттинг** | Изоляция чистого вокала и инструментала моделью `htdemucs` с GPU-ускорением |
| **RVC-инференс** | Преобразование тембра через локальный API-сервер Applio v3.6.5 (RMVPE + индексный поиск) |
| **Сведение в пачке** | Финальный микс вокала и минуса через FFmpeg с настраиваемым балансом громкости (50–200%) |
| **Очередь обработки** | Асинхронный воркер на `asyncio.Queue` с защитой от OOM и трекингом позиции в очереди |
| **Студийный рэк** | Терминальный HUD с VU-метром, автоопределением GPU VRAM и мастером установки |
| **Автозагрузка ассетов** | Скачивание Applio 3.6.5 и стартовых моделей (Валакас, Дора) из релизов прямо при запуске |
| **Админ-консоль** | Отдельная CLI-панель: аналитика, просмотр чатов, бан по ID, рассылки и выгрузка треков |

---

## Структура проекта

```text
MashMachine/
├── applio/               # локальный инференс-сервер Applio (порт 6969)
│   ├── assets/audios/    # буфер промежуточных аудиодорожек для RVC
│   └── logs/             # веса и индексы моделей голосов (.pth, .index)
├── data/
│   └── mashuper.db       # база SQLite: пользователи, статистика, логи сообщений
├── downloads/            # входящие аудиофайлы из Telegram
├── processed/            # готовые экспортированные мешапы
├── utils/
│   ├── audio_merge.py    # нормализация и сведение дорожек через FFmpeg
│   ├── cleanup.py        # сборщик мусора и удаление временных файлов
│   ├── console_ui.py     # студийный рэк, прогресс-бары и автозагрузка компонентов
│   ├── demucs_split.py   # стем-сплиттинг вокала и инструментала
│   └── rvc_applio.py     # клиент SSE-стриминга и вызова Applio API
├── admin_cli.py          # интерактивная консоль администратора
├── bot.py                # ядро Telegram-бота на Aiogram 3
├── config.py             # центральный конфиг и параметры по умолчанию
├── run.py                # главная точка входа: проверка окружения, рэк и запуск
├── requirements.txt      # список зависимостей Python
├── run_mashuper.bat      # автозапуск бота с watchdog-перезапуском для Windows
└── run_admin.bat         # быстрый запуск панели администратора
```

---

## Системные требования

| Компонент | Минимальные | Рекомендуемые |
| :--- | :--- | :--- |
| **Видеокарта** | NVIDIA GPU 4–6 ГБ VRAM / Многопоточный CPU | NVIDIA RTX (8+ ГБ VRAM, CUDA) |
| **Оперативная память** | 8 ГБ RAM | 16 ГБ RAM |
| **Операционная система** | Windows 10/11, Linux (Ubuntu/Debian) | Windows 11 / Ubuntu 22.04+ |
| **Python** | Python 3.10 – 3.11 | Python 3.10 |

---

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/BearCodexx/MashMachine.git
cd MashMachine
```

### 2. Создание окружения

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

> [!IMPORTANT]
> Для инференса на GPU обязательно установите PyTorch с поддержкой CUDA 12.1:
> ```bash
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
> ```
> Также убедитесь, что в системе установлен и доступен в `PATH` бинарник [FFmpeg](https://ffmpeg.org/download.html).

### 4. Конфигурация (.env)

Создайте файл `.env` в корне проекта (или введите токен интерактивно при первом запуске):

```env
BOT_TOKEN=123456789:AAExampleTokenHere
ADMIN_IDS=1234567890
APPLIO_DIR=./applio
```

### 5. Запуск

```bash
# Windows (в один клик):
run_mashuper.bat

# Терминал (Windows / Linux):
python run.py
```

> [!NOTE]
> При первом запуске консольный мастер определит состояние системы:
> - Предложит скачать чистую сборку **Applio v3.6.5** с Hugging Face (~3.5 ГБ) либо указать существующую папку;
> - Автоматически загрузит стартовый пак моделей голосов (**Валакас**, **Дора**) из GitHub Releases;
> - Запустит локальный сервис Applio на `http://127.0.0.1:6969` в фоне.

---

## Сводная таблица команд

### Команды Telegram-бота

| Команда | Назначение |
| :--- | :--- |
| `/start` | Главное меню и краткая справка по работе |
| `/valakas` | Быстрое переключение текущего голоса на Глада Валакаса |
| `/dora` | Быстрое переключение текущего голоса на Дору |
| `/settings` | Выбор модели голоса и регулировка громкости вокала (50–200%) |
| `/stats` | Личная статистика генераций и остаток дневного лимита |
| `/cancel` | Сброс зависшей задачи или отмена текущего действия |

### Команды консоли администратора (`admin_cli.py`)

| Команда | Аргументы | Назначение |
| :--- | :--- | :--- |
| `stats` | — | Общая сводка (пользователи, генерации, блокировки) |
| `users` | — | Список зарегистрированных пользователей и их активность |
| `chat` | `<tg_id>` | Лог последних сообщений диалога с пользователем |
| `msg` | `<tg_id> <текст>` | Отправка прямого сообщения пользователю от имени бота |
| `block` | `<tg_id>` | Добавление пользователя в черный список |
| `unblock` | `<tg_id>` | Снятие блокировки с пользователя |
| `broadcast` | `<текст>` | Массовая рассылка всем пользователям бота |
| `file` | `<tg_id>` | Копирование последнего сгенерированного файла пользователя в текущую папку |
| `exit` | — | Выход из панели администратора |

---

## Поддержка проекта

Если проект **MashMachine** оказался для вас полезным, вы можете поддержать дальнейшую разработку и добавление новых возможностей:

[![DonationAlerts](https://img.shields.io/badge/DonationAlerts-Поддержать_проект-FF5900?style=for-the-badge&logo=donationalerts&logoColor=white)](https://www.donationalerts.com/r/bearcodexdev)

---

## Лицензия

Распространяется под свободной лицензией **MIT**. Подробности в файле `LICENSE`.

<br>

<div align="center">

<sub>Разработано BearCodex</sub>

</div>
