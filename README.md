# 🎭 MashuperBot — RVC Voice Changer Bot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Aiogram](https://img.shields.io/badge/Aiogram-3.16.0-green)
![RVC](https://img.shields.io/badge/RVC-Applio-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

**Telegram-бот для создания мешапов с преобразованием голоса через RVC**

[![Telegram](https://img.shields.io/badge/Telegram-Канал-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/bearcodex)

</div>

---

## ✨ Что умеет бот

| Функция | Описание |
|---------|----------|
| 🎤 **Разделение вокала** | Demucs разделяет аудио на вокал и инструментал |
| 🎭 **Конвертация голоса** | Applio RVC изменяет тембр голоса |
| 🔊 **Склейка треков** | Обработанный вокал + оригинальный инструментал |
| 🎚 **Регулировка громкости** | От 50% до 200% относительно исходника |
| 📊 **Статистика** | 3 обработки в день для обычных пользователей |
| 👑 **Админ-панель** | Управление пользователями, рассылки, статистика |

---

## 🚀 Установка и запуск

### 1. Установите Applio

> **Важно:** Applio должен быть **запущен на порту 6969** до старта бота.

Почему Applio, а не RVC WebUI? RVC WebUI не обновляется (на 2026 год поддержка Blackwell отсутствует), зависимости типа PyTorch устарели, CUDA 13-го поколения не поддерживается, CPU режим — слишком медленно.

[Скачать Applio](https://github.com/IAHispano/Applio)

### 2. Установите зависимости

pip install -r requirements.txt

### ⚠️ Важно про PyTorch

Если у вас NVIDIA + CUDA, убедитесь, что PyTorch установлен с поддержкой вашей версии CUDA. Иначе Demucs будет работать через CPU, а это очень медленно.

Пример для CUDA 12.x:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

Если у вас AMD, Intel или нет CUDA — Applio может не заработать без NVIDIA GPU. Варианты: использовать CPU (очень медленно) либо адаптировать инференс под RVC WebUI с DirectML/ROCm.

---

### 3. Настройте config.py

BOT_TOKEN = "токен_твоего_бота"

Остальные параметры (Applio URL, pitch map и т.д.) можно оставить по умолчанию.

---

### 4. Запустите бота

python bot.py

Готово 🎉

---

## 🎤 Добавление своих голосов

Откройте `bot.py` и найдите переменную `AVAILABLE_VOICES`. Добавьте новую модель:

"my_voice": {
    "name": "Мой голос",
    "lang": "Русский",
    "gender": "Мужской",
    "pitch_map": {
        "Грубый мужской": -18,
        "Мужской": -20,
        "Грубый женский": -21,
        "Женский": -24
    }
},

---

## 📁 Подготовка модели

В папке `logs` (где установлен Applio) создайте папку с именем модели:

applio/logs/my_voice/

Поместите туда файлы модели:
- my_voice.pth
- my_voice.index

> ⚠️ Названия `.pth`, `.index`, папки и ключа модели должны полностью совпадать.

Пример структуры:
logs/
└── my_voice/
    ├── my_voice.pth
    └── my_voice.index

---

## 💡 Советы

- Для быстрой обработки рекомендуется NVIDIA GPU
- Без CUDA обработка может занимать несколько минут
- Голоса сохраняются для каждого пользователя отдельно
- Админ-панель запускается параллельно с ботом
- Если появляются ошибки инференса — сначала проверьте Applio и CUDA

---

## 🤝 Поддержка проекта

<div align="center">

[![DonateAlerts](https://img.shields.io/badge/DonateAlerts-Поддержать-orange?style=for-the-badge)](https://www.donationalerts.com/r/bearcodexdev)

</div>

---

<div align="center">

<sub>Made with ☕, BearCodex (bearcodexx)</sub>

</div>

