import os

# загрузка переменных из .env если файл существует
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# токен бота можно задать в .env или строкой ниже
BOT_TOKEN = os.getenv("BOT_TOKEN", "токен_твоего_бота")

# id админов с бесконечными генерациями
ADMIN_IDS = [1234567890]

# прокси
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "false").lower() in ("true", "1")
PROXY_URL = os.getenv("PROXY_URL", "socks5://login:password@ip:port")

# каналы для обязательной подписки
REQUIRED_CHANNELS = [
    # ("@example", "https://t.me/example", "Название")
]

# пути проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
DATA_DIR = os.path.join(BASE_DIR, "data")

# путь к каталогу applio (можно переопределить через .env)
APPLIO_DIR = os.getenv("APPLIO_DIR", os.path.join(BASE_DIR, "applio"))

# лимиты на загрузку файлов
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25")) # максимальный размер аудио в мегабайтах

# параметры подключения к applio
APPLIO_HOST = os.getenv("APPLIO_HOST", "127.0.0.1")
APPLIO_PORT = int(os.getenv("APPLIO_PORT", "6969"))
APPLIO_URL = f"http://{APPLIO_HOST}:{APPLIO_PORT}/gradio_api/queue/join"
SSE_URL = f"http://{APPLIO_HOST}:{APPLIO_PORT}/gradio_api/queue/data"
APPLIO_FN_INDEX = int(os.getenv("APPLIO_FN_INDEX", "59"))
APPLIO_TRIGGER_ID = int(os.getenv("APPLIO_TRIGGER_ID", "109"))

# параметры rvc
RVC_INDEX_RATE = float(os.getenv("RVC_INDEX_RATE", "0.75"))
RVC_F0_METHOD = os.getenv("RVC_F0_METHOD", "rmvpe")

# модель demucs
DEMUCS_MODEL = os.getenv("DEMUCS_MODEL", "htdemucs")

# путь к исполняемому файлу ffmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")