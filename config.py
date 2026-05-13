import os

BOT_TOKEN = "токен_твоего_бота"

# админы (у них бесконечные генерации)
ADMIN_IDS = [1234567890] # id telegram (можно узнать прямо в боте)

# прокси
PROXY_ENABLED = False # поставить true, если нужен прокси
PROXY_URL = "socks5://login:password@ip:port" # или http

# каналы для подписки
REQUIRED_CHANNELS = [
    ("@example", "https://t.me/example", "Название")
    # ("@another", "https://t.me/channel", "Доп канал"),
]

# директории папок
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

APPLIO_URL = "http://127.0.0.1:6969/gradio_api/queue/join" # эндпоинт апплио, который на порту 6969
SSE_URL = "http://127.0.0.1:6969/gradio_api/queue/data"
APPLIO_FN_INDEX = 59
APPLIO_TRIGGER_ID = 109
'''
Точно не знаю, но возможно fn_index и trigger_id могут различаться,
поэтому если ошибка, поищите их значения в F12 в конце payload пункта Join после нажатия на кнопку конвертации
'''
# параметры rvc (можно менять)
RVC_INDEX_RATE = 0.75
RVC_F0_METHOD = "rmvpe"
# RVC_PROTECT = 0.33 (после обновления applio не знаю, где он)

# demucs
DEMUCS_MODEL = "htdemucs"       # можно "htdemucs", "mdx", "demucs"

# ffmpeg
FFMPEG_PATH = "ffmpeg" # если ffmpeg в PATH