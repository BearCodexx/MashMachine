import os
import sys
import time
import socket
import zipfile
import urllib.request
import subprocess
from pathlib import Path

# цветовая палитра для студийного терминала
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

APPLIO_DOWNLOAD_URL = "https://huggingface.co/IAHispano/Applio/resolve/main/Compiled/Windows/ApplioV3.6.5.zip"

def enable_ansi_windows(): # включение поддержки ansi escape кодов в консоли windows
    if os.name == "nt":
        os.system("")
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

def print_banner(version="3.6.5", device="CUDA / NVIDIA"): # вывод студийного логотипа и vu метра
    enable_ansi_windows()
    banner = f"""{MAGENTA}{BOLD}
  __  __           _                               
 |  \\/  |         | |                              
 | \\  / | __ _ ___| |__  _   _ _ __   ___ _ __     
 | |\\/| |/ _` / __| '_ \\| | | | '_ \\ / _ \\ '__|    
 | |  | | (_| \\__ \\ | | | |_| | |_) |  __/ |       
 |_|  |_|\\__,_|___/_| |_|\\__,_| .__/ \\___|_|       
                              | |                  
                              |_|                  {RESET}
{CYAN}┌─ STUDIO RACK ────────────────────────────────────────────────────────┐
│  {BOLD}ENGINE:{RESET}{CYAN} RVC v2 + DEMUCS v4  │  {BOLD}RATE:{RESET}{CYAN} 48.0 kHz  │  {BOLD}TARGET:{RESET}{CYAN} MASHUP MIX   │
│  {BOLD}DEVICE:{RESET}{CYAN} {device:<19} │  {BOLD}APPLIO:{RESET}{CYAN} v{version:<8} │  {BOLD}CHANNELS:{RESET}{CYAN} STEREO     │
│  VU: {GREEN}[■■■■■■■■■■■■■■■■■■■■■■■■{YELLOW}■■■■{RED}░░░░]{RESET}{CYAN} -3.0 dB    PEAK: 0.0 dB │
└──────────────────────────────────────────────────────────────────────┘{RESET}
"""
    print(banner)

def log_event(badge: str, message: str, color=CYAN): # форматированный вывод логов в студийном стиле
    t = time.strftime("%H:%M:%S")
    b_colored = f"{color}{BOLD}[{badge:<6}]{RESET}"
    print(f"{GRAY}[{t}]{RESET} {b_colored} {message}")

def is_port_open(host="127.0.0.1", port=6969, timeout=1.0) -> bool: # проверка доступности порта applio
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

def check_applio_installed(applio_path: str) -> bool: # проверка наличия ключевых файлов applio
    if not applio_path or not os.path.exists(applio_path):
        return False
    app_py = os.path.join(applio_path, "app.py")
    core_py = os.path.join(applio_path, "core.py")
    run_bat = os.path.join(applio_path, "run-applio.bat")
    return os.path.exists(app_py) or os.path.exists(core_py) or os.path.exists(run_bat)

def update_env_variable(key: str, value: str, env_path=".env"): # сохранение переменной в локальный .env
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler): # редирект без утечки auth заголовка на aws s3
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req and ("amazonaws.com" in newurl or "objects.githubusercontent.com" in newurl):
            if "Authorization" in new_req.headers:
                del new_req.headers["Authorization"]
        return new_req

def get_github_token() -> str: # получение github токена из окружения или git credential
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        proc = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, _ = proc.communicate(input="protocol=https\nhost=github.com\n\n", timeout=5)
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

def download_file_with_progress(url: str, output_path: str, custom_headers: dict = None): # загрузка файла с визуальным прогресс баром
    log_event("NET", f"Подключение к серверу загрузки: {url}", BLUE)
    headers = {"User-Agent": "MashMachine-Applio/1.0"}
    if custom_headers:
        headers.update(custom_headers)
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(SafeRedirectHandler)

    with opener.open(req) as response:
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024 # 1 мб чанк
        start_time = time.time()

        with open(output_path, "wb") as out_file:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)

                elapsed = max(0.1, time.time() - start_time)
                speed = (downloaded / (1024 * 1024)) / elapsed
                percent = (downloaded / total_size) * 100 if total_size else 0

                bar_len = 24
                filled = int(bar_len * percent / 100)
                bar = f"{GREEN}{'■' * filled}{GRAY}{'░' * (bar_len - filled)}{RESET}"

                dl_mb = downloaded / (1024 * 1024)
                tot_mb = total_size / (1024 * 1024)
                sys.stdout.write(f"\r  {CYAN}Загрузка:{RESET} [{bar}] {BOLD}{percent:5.1f}%{RESET} ({dl_mb:5.0f}/{tot_mb:5.0f} МБ) {YELLOW}{speed:4.1f} МБ/с{RESET}  ")
                sys.stdout.flush()

    print()
    log_event("OK", "Архив успешно скачан на диск", GREEN)

def extract_zip_with_progress(zip_path: str, extract_to: str): # распаковка zip архива с прогрессом
    log_event("UNZIP", f"Распаковка файлов в папку: {extract_to}", YELLOW)
    os.makedirs(extract_to, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        total_files = len(members)

        for idx, member in enumerate(members, 1):
            zf.extract(member, extract_to)
            if idx % 150 == 0 or idx == total_files:
                percent = (idx / total_files) * 100
                bar_len = 24
                filled = int(bar_len * percent / 100)
                bar = f"{MAGENTA}{'■' * filled}{GRAY}{'░' * (bar_len - filled)}{RESET}"
                sys.stdout.write(f"\r  {CYAN}Распаковка:{RESET} [{bar}] {BOLD}{percent:5.1f}%{RESET} ({idx}/{total_files} файлов)  ")
                sys.stdout.flush()

    print()
    log_event("OK", "Распаковка завершена", GREEN)

def check_installed_models(applio_dir: str) -> list: # поиск установленных моделей голосов в logs
    logs_dir = os.path.join(applio_dir, "logs")
    if not os.path.exists(logs_dir):
        return []
    installed = []
    for item in os.listdir(logs_dir):
        sub = os.path.join(logs_dir, item)
        if os.path.isdir(sub):
            pths = [f for f in os.listdir(sub) if f.lower().endswith(".pth")]
            if pths:
                installed.append(item)
    return installed

def download_starter_voices(applio_dir: str, base_dir: str) -> bool: # скачивание и распаковка стартового пака моделей
    logs_dir = os.path.join(applio_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    temp_zip = os.path.join(base_dir, "starter_voices_pack.zip")

    log_event("VOICES", "Загрузка стартового пака моделей (Валакас, Дора)...", CYAN)

    token = get_github_token()
    download_ok = False

    # попытка прямой загрузки из публичного релиза
    try:
        direct_url = "https://github.com/BearCodexx/MashMachine/releases/download/v1.0.0/starter_voices.zip"
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        download_file_with_progress(direct_url, temp_zip, custom_headers=headers)
        download_ok = True
    except Exception:
        # фоллбэк на загрузку через github api для приватного репозитория
        try:
            api_url = "https://api.github.com/repos/BearCodexx/MashMachine/releases/assets/645107362"
            headers = {"Accept": "application/octet-stream"}
            if token:
                headers["Authorization"] = f"token {token}"
            download_file_with_progress(api_url, temp_zip, custom_headers=headers)
            download_ok = True
        except Exception as e:
            log_event("ERR", f"Не удалось загрузить стартовые модели: {e}", RED)
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
            return False

    if download_ok and os.path.exists(temp_zip):
        try:
            extract_zip_with_progress(temp_zip, logs_dir)
            log_event("READY", f"Стартовые модели успешно распакованы в {logs_dir}", GREEN)
            return True
        except Exception as e:
            log_event("ERR", f"Ошибка распаковки архива моделей: {e}", RED)
            return False
        finally:
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
    return False

def prompt_starter_voices(applio_dir: str, base_dir: str): # диалог скачивания стартового пака если моделей нет
    installed = check_installed_models(applio_dir)
    if "valakas" in installed and "dora" in installed:
        return
    print()
    log_event("VOICES", "Стартовый пак моделей голосов (Валакас, Дора) доступен в релизе", CYAN)
    try:
        ans = input(f" {CYAN}► Скачать стартовый пак моделей? [Y/n]:{RESET} ").strip().lower()
        if ans in ("", "y", "yes", "д", "да"):
            download_starter_voices(applio_dir, base_dir)
    except (EOFError, KeyboardInterrupt):
        print()

def run_setup_wizard(current_applio_dir: str, base_dir: str) -> str: # интерактивный мастер первичной настройки applio
    enable_ansi_windows()

    print(f"""
{CYAN}╔══════════════════════════════════════════════════════════════════════╗
║               МАСТЕР УСТАНОВКИ ДВИЖКА ГОЛОСА APPLIO                  ║
╚══════════════════════════════════════════════════════════════════════╝{RESET}

{YELLOW}Движок преобразования голоса (Applio RVC) не обнаружен по пути:{RESET}
-> {GRAY}{current_applio_dir}{RESET}

Для генерации мешапов выберите способ настройки:

  {BOLD}[1]{RESET} {GREEN}Установить Applio 3.6.5 автоматически{RESET} (скачивание с Hugging Face ~3.5 ГБ)
  {BOLD}[2]{RESET} {BLUE}Указать путь к готовой папке Applio{RESET} на компьютере (если уже скачан)
  {BOLD}[3]{RESET} {GRAY}Пропустить настройку{RESET} (запустить бота без инференса RVC)
""")

    while True:
        try:
            choice = input(f" {CYAN}► Выберите вариант [1/2/3]:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nОтмена настройки.")
            return current_applio_dir

        if choice == "1":
            target_dir = os.path.join(base_dir, "applio")
            temp_zip = os.path.join(base_dir, "applio_v3.6.5_installer.zip")
            print()
            log_event("SETUP", f"Старт автоматической установки в {target_dir}", CYAN)
            try:
                download_file_with_progress(APPLIO_DOWNLOAD_URL, temp_zip)
                extract_zip_with_progress(temp_zip, target_dir)
                if os.path.exists(temp_zip):
                    os.remove(temp_zip)

                update_env_variable("APPLIO_DIR", target_dir)
                log_event("READY", "Applio 3.6.5 установлен и сохранен в .env", GREEN)

                # загрузка стартовых моделей после установки
                prompt_starter_voices(target_dir, base_dir)

                return target_dir
            except Exception as e:
                log_event("ERR", f"Ошибка автоматической установки: {e}", RED)
                if os.path.exists(temp_zip):
                    try:
                        os.remove(temp_zip)
                    except Exception:
                        pass
                print("Попробуйте указать путь вручную (вариант 2) или повторить попытку.")

        elif choice == "2":
            print()
            while True:
                path_input = input(f" {CYAN}► Введите путь к папке с Applio:{RESET} ").strip().strip('"').strip("'")
                if not path_input:
                    break
                expanded = os.path.abspath(os.path.expanduser(path_input))
                if check_applio_installed(expanded):
                    update_env_variable("APPLIO_DIR", expanded)
                    log_event("OK", f"Путь подтвержден и сохранен в .env: {expanded}", GREEN)

                    # загрузка стартовых моделей если еще нет
                    prompt_starter_voices(expanded, base_dir)

                    return expanded
                else:
                    log_event("WARN", f"В каталоге {expanded} не найден app.py или core.py", YELLOW)
                    retry = input(" Попробовать другой путь? [y/n]: ").strip().lower()
                    if retry not in ("y", "yes", "д", "да"):
                        break

        elif choice == "3":
            log_event("SKIP", "Запуск без настройки Applio. RVC будет временно недоступен", YELLOW)
            return current_applio_dir

        else:
            print(" Введите 1, 2 или 3.")

def ensure_applio_service(applio_dir: str, host="127.0.0.1", port=6969) -> bool: # проверка и запуск фонового сервиса applio
    if is_port_open(host, port):
        log_event("APPLIO", f"Сервис уже активен на http://{host}:{port}", GREEN)
        return True

    if not check_applio_installed(applio_dir):
        log_event("WARN", f"Каталог Applio не настроен ({applio_dir}). Инференс недоступен", YELLOW)
        return False

    log_event("START", f"Запускаю фоновый сервис Applio (порт {port})...", MAGENTA)

    env_python = os.path.join(applio_dir, "env", "python.exe")
    app_py = os.path.join(applio_dir, "app.py")
    run_bat = os.path.join(applio_dir, "run-applio.bat")

    cmd = None
    if os.path.exists(env_python) and os.path.exists(app_py):
        cmd = [env_python, "app.py", "--open"]
    elif os.path.exists(run_bat):
        cmd = ["cmd.exe", "/c", run_bat]

    if not cmd:
        log_event("ERR", f"Не найден исполняемый файл для запуска в {applio_dir}", RED)
        return False

    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    try:
        subprocess.Popen(cmd, cwd=applio_dir, creationflags=flags)
    except Exception as e:
        log_event("ERR", f"Не удалось запустить процесс Applio: {e}", RED)
        return False

    # ожидание выхода сервиса в онлайн
    max_wait = 40
    start_t = time.time()
    while time.time() - start_t < max_wait:
        if is_port_open(host, port):
            log_event("ONLINE", f"Сервис Applio успешно вышел в онлайн: http://{host}:{port}", GREEN)
            return True
        passed = int(time.time() - start_t)
        dots = "■" * ((passed % 6) + 1)
        sys.stdout.write(f"\r  {GRAY}[ОЖИДАНИЕ]{RESET} Инициализация нейросетей Applio [{dots:<6}] {passed}с...  ")
        sys.stdout.flush()
        time.sleep(1.0)

    print()
    log_event("WARN", "Таймаут ожидания Applio. Бот продолжит запуск, проверьте окно Applio", YELLOW)
    return False
