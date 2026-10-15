import os
import sys
import asyncio
import torch

from utils.console_ui import (
    enable_ansi_windows,
    print_banner,
    log_event,
    check_applio_installed,
    check_installed_models,
    prompt_starter_voices,
    run_setup_wizard,
    ensure_applio_service,
    update_env_variable,
    CYAN,
    MAGENTA,
    GREEN,
    YELLOW,
    RED,
    BLUE,
)
import config
from bot import main as bot_main

def detect_device_name() -> str: # определение доступного аппаратного ускорения
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return f"{gpu_name} ({vram_gb:.1f}GB)"
    return "CPU (режим без CUDA)"

def setup_bot_token_if_needed(): # запрос токена телеграм бота при первом запуске
    if config.BOT_TOKEN == "токен_твоего_бота" or not config.BOT_TOKEN:
        print()
        log_event("CONFIG", "Токен Telegram-бота еще не настроен", YELLOW)
        try:
            token = input(" ► Введите токен бота от @BotFather: ").strip()
            if token and ":" in token:
                update_env_variable("BOT_TOKEN", token)
                config.BOT_TOKEN = token
                log_event("OK", "Токен сохранен в .env", GREEN)
            else:
                log_event("WARN", "Токен не введен. Бот не сможет подключиться к Telegram API", RED)
        except (EOFError, KeyboardInterrupt):
            pass

def main(): # главная точка входа приложения
    enable_ansi_windows()

    # определение устройства и вывод студийного рэка
    device_label = detect_device_name()
    print_banner(version="3.6.5", device=device_label)

    # шаг 1: проверка установки applio
    if not check_applio_installed(config.APPLIO_DIR):
        chosen_dir = run_setup_wizard(config.APPLIO_DIR, config.BASE_DIR)
        config.APPLIO_DIR = chosen_dir

    # шаг 2: проверка сервиса applio на порту 6969
    if check_applio_installed(config.APPLIO_DIR):
        ensure_applio_service(config.APPLIO_DIR, config.APPLIO_HOST, config.APPLIO_PORT)
        installed_models = check_installed_models(config.APPLIO_DIR)
        if not installed_models:
            log_event("WARN", "В applio/logs/ нет файлов моделей .pth", YELLOW)
            prompt_starter_voices(config.APPLIO_DIR, config.BASE_DIR)
            installed_models = check_installed_models(config.APPLIO_DIR)
        if installed_models:
            log_event("VOICES", f"Готовые модели для инференса: {', '.join(installed_models)}", GREEN)

    # шаг 3: проверка токена
    setup_bot_token_if_needed()

    if config.BOT_TOKEN == "токен_твоего_бота" or not config.BOT_TOKEN:
        log_event("STOP", "Запуск отменен: укажите BOT_TOKEN в файле .env или config.py", RED)
        return

    # шаг 4: запуск бота
    log_event("READY", "Студийный движок готов. Запуск Telegram-бота...", GREEN)
    try:
        asyncio.run(bot_main())
    except (KeyboardInterrupt, SystemExit):
        print()
        log_event("STOP", "Сервис MashuperBot остановлен пользователем", YELLOW)
    except Exception as e:
        log_event("CRASH", f"Критическая ошибка: {e}", RED)

if __name__ == "__main__":
    main()
