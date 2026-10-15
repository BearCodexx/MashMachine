import os
import time
import uuid
import asyncio
import logging
import datetime
import pytz
import soundfile as sf
import numpy as np

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    PROXY_ENABLED,
    PROXY_URL,
    REQUIRED_CHANNELS,
    BASE_DIR,
    DOWNLOADS_DIR,
    PROCESSED_DIR,
    MAX_FILE_SIZE_MB,
)
from utils.demucs_split import split_vocals_instrumental
from utils.rvc_applio import applio_process_voice
from utils.audio_merge import merge_vocals_instrumental
from utils.cleanup import cleanup_files
from utils.console_ui import log_event, CYAN, MAGENTA, GREEN, YELLOW, BLUE
from admin_cli import (
    init_db,
    add_user,
    update_stats,
    is_blocked,
    save_message,
    get_user_stats,
    update_user_calls_today,
    increment_calls_total,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# инициализация бота и диспетчера
session = AiohttpSession(proxy=PROXY_URL) if PROXY_ENABLED else None
try:
    bot = Bot(token=BOT_TOKEN, session=session)
except Exception:
    # фиктивный токен на случай импорта и линтинга без боевого токена
    bot = Bot(token="123456789:AAFakeTokenForModuleImportAndLintingOK", session=session)
dp = Dispatcher(storage=MemoryStorage())
bot_start_time = datetime.datetime.now(datetime.timezone.utc)

# поддерживаемые модели голосов и их пич-маппинг
AVAILABLE_VOICES = {
    "valakas": {
        "name": "Валакас",
        "lang": "Русский",
        "gender": "Мужской (грубый)",
        "pitch_map": {
            "Грубый мужской": -18,
            "Мужской": -20,
            "Грубый женский": -21,
            "Женский": -24,
        },
    },
    "dora": {
        "name": "Дора",
        "lang": "Русский",
        "gender": "Женский (молодой)",
        "pitch_map": {
            "Грубый мужской": 5,
            "Мужской": 3,
            "Грубый женский": 3,
            "Женский": 0,
        },
    },
}

# персональный выбор голоса для каждого пользователя
user_selected_voices = {}

# состояние FSM диалога
class VoiceSelection(StatesGroup):
    waiting_for_gender = State() # выбор ведущего типа вокала в исходнике
    waiting_for_volume = State() # выбор процента громкости вокала

# внутренняя очередь задач
processing_queue = asyncio.Queue()
queue_positions = {}
task_messages = {}
queue_lock = asyncio.Lock()
current_task_running = False

# проверка подписок на каналы
async def is_subscribed(bot_instance: Bot, user_id: int) -> bool:
    for channel_id, _, _ in REQUIRED_CHANNELS:
        try:
            cid = int(channel_id) if not channel_id.startswith("@") else channel_id
            member = await bot_instance.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status not in ["member", "creator", "administrator", "restricted"]:
                return False
        except Exception:
            return False
    return True

async def get_unsubscribed_channels(bot_instance: Bot, user_id: int) -> list: # поиск неподписанных каналов
    unsub = []
    for channel_id, channel_url, channel_name in REQUIRED_CHANNELS:
        try:
            cid = int(channel_id) if not channel_id.startswith("@") else channel_id
            member = await bot_instance.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status not in ["member", "creator", "administrator", "restricted"]:
                unsub.append((channel_id, channel_url, channel_name))
        except Exception:
            unsub.append((channel_id, channel_url, channel_name))
    return unsub

def get_subscription_keyboard(unsubscribed_channels: list) -> InlineKeyboardMarkup: # инлайн кнопки со ссылками на каналы
    kb = [[InlineKeyboardButton(text=f"Подписаться на {name}", url=url)] for _, url, name in unsubscribed_channels]
    kb.append([InlineKeyboardButton(text="Проверить подписки", callback_data="check_all_subscriptions")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# декораторы

def check_time(func): # отсеивание старых сообщений при старте
    async def wrapper(message: types.Message, *args, **kwargs):
        global bot_start_time
        msg_time = message.date.replace(tzinfo=datetime.timezone.utc) if message.date.tzinfo is None else message.date
        if msg_time < bot_start_time:
            return
        return await func(message, *args, **kwargs)
    return wrapper

def check_blocked(func): # проверка на бан
    async def wrapper(message: types.Message, *args, **kwargs):
        if is_blocked(message.from_user.id):
            await message.answer("Доступ к боту заблокирован администратором.")
            return
        return await func(message, *args, **kwargs)
    return wrapper

def check_subscription(func): # проверка обязательной подписки
    async def wrapper(message: types.Message, *args, **kwargs):
        uid = message.from_user.id
        if not REQUIRED_CHANNELS:
            return await func(message, *args, **kwargs)
        unsub = await get_unsubscribed_channels(bot, uid)
        if not unsub:
            return await func(message, *args, **kwargs)
        ch_list = "\n".join([f"• {name} ({cid})" for cid, _, name in unsub])
        text = (
            "Доступ ограничен.\n\n"
            "Для использования бота необходимо подписаться на каналы:\n\n"
            f"{ch_list}\n\n"
            "После подписки нажмите кнопку ниже."
        )
        await message.answer(text, reply_markup=get_subscription_keyboard(unsub))
    return wrapper

# лимиты и статистика

def can_make_processing(user_id: int) -> bool: # проверка дневного лимита генераций
    if user_id in ADMIN_IDS:
        return True
    stats = get_user_stats(user_id)
    today = datetime.date.today().isoformat()
    if not stats or stats["last_call_date"] != today:
        return True
    return stats["calls_today"] < 3

def increment_processing_count(user_id: int, username: str): # учет использования попыток
    today = datetime.date.today().isoformat()
    if user_id in ADMIN_IDS:
        increment_calls_total(user_id, username)
        return
    stats = get_user_stats(user_id)
    calls_today = 1 if not stats or stats["last_call_date"] != today else stats["calls_today"] + 1
    update_user_calls_today(user_id, username, calls_today)
    increment_calls_total(user_id, username)

def get_user_stats_text(user_id: int, username: str) -> str: # сводка пользователя в html
    stats = get_user_stats(user_id)
    today = datetime.date.today().isoformat()
    calls_today = stats["calls_today"] if stats and stats["last_call_date"] == today else 0
    total_calls = stats["total_calls"] if stats else 0
    available = "без ограничений" if user_id in ADMIN_IDS else f"{max(0, 3 - calls_today)}/3"
    current_v = user_selected_voices.get(user_id, "valakas")
    voice_name = AVAILABLE_VOICES.get(current_v, {}).get("name", "Валакас")
    uname = f"@{username}" if username else "не указан"

    return (
        "<b>Ваша статистика</b>\n\n"
        f"<b>Пользователь:</b> {uname}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Выбранный голос:</b> {voice_name}\n"
        f"<b>Осталось на сегодня:</b> {available}\n"
        f"<b>Всего обработок:</b> {total_calls}\n"
    )

# клавиатуры

def get_gender_keyboard() -> InlineKeyboardMarkup: # выбор типа вокала в песне
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Грубый мужской", callback_data="gender_Грубый мужской")],
        [InlineKeyboardButton(text="Мужской", callback_data="gender_Мужской")],
        [InlineKeyboardButton(text="Грубый женский", callback_data="gender_Грубый женский")],
        [InlineKeyboardButton(text="Женский", callback_data="gender_Женский")],
    ])

def get_volume_keyboard() -> InlineKeyboardMarkup: # выбор громкости обработанного вокала
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50%", callback_data="volume_50"),
            InlineKeyboardButton(text="75%", callback_data="volume_75"),
            InlineKeyboardButton(text="100%", callback_data="volume_100"),
        ],
        [
            InlineKeyboardButton(text="125%", callback_data="volume_125"),
            InlineKeyboardButton(text="150%", callback_data="volume_150"),
            InlineKeyboardButton(text="200%", callback_data="volume_200"),
        ]
    ])

def get_main_keyboard() -> ReplyKeyboardMarkup: # основное меню
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Библиотека голосов"), KeyboardButton(text="Моя статистика")]
        ],
        resize_keyboard=True
    )

def build_library_text(user_id: int) -> str: # список моделей и команды переключения
    curr = user_selected_voices.get(user_id, "valakas")
    lines = ["<b>Библиотека доступных голосов:</b>\n"]
    for k, v in AVAILABLE_VOICES.items():
        mark = " (выбран)" if k == curr else ""
        lines.append(f"• <b>{v['name']}</b>{mark} — {v['lang']}, {v['gender']}\n  /{k} — выбрать этот голос")
    return "\n".join(lines)

# фоновый воркер очереди задач

async def update_queue_messages(): # обновление номеров в очереди
    async with queue_lock:
        for sid, pos in list(queue_positions.items()):
            msg = task_messages.get(sid)
            if msg and pos > 0:
                try:
                    await msg.edit_text(f"Ожидание в очереди... Перед вами задач: {pos}")
                except Exception:
                    pass

async def queue_worker(): # постоянный потребитель очереди
    global current_task_running
    while True:
        task_data = await processing_queue.get()
        current_task_running = True
        sid = task_data[0]
        status_msg = task_messages.get(sid)

        async with queue_lock:
            queue_positions.pop(sid, None)
            # смещаем позиции остальных
            for other_sid in queue_positions:
                if queue_positions[other_sid] > 0:
                    queue_positions[other_sid] -= 1

        await update_queue_messages()

        try:
            await process_audio_task(*task_data)
        except FileNotFoundError as e:
            logger.error("модель не найдена: %s", e)
            if status_msg:
                try:
                    await status_msg.edit_text("Ошибка: файлы выбранной модели голоса (.pth) не найдены на сервере. Пожалуйста, обратитесь к администратору.")
                except Exception:
                    pass
        except Exception as e:
            logger.exception("ошибка при обработке задачи: %s", e)
            if status_msg:
                try:
                    await status_msg.edit_text(f"Ошибка при обработке: {e}")
                except Exception:
                    pass
        finally:
            async with queue_lock:
                task_messages.pop(sid, None)
            processing_queue.task_done()
            current_task_running = False

# конвейер обработки аудио

async def process_audio_task(
    sid: str,
    status_msg: types.Message,
    original_path: str,
    source_message: types.Message,
    original_title: str,
    original_performer: str,
    voice: str,
    pitch: int,
    volume_percent: int = 100
):
    vp = ip = pvp = fp = None
    uid = source_message.from_user.id
    try:
        log_event("DEMUCS", f"Разделение дорожек: {original_title or 'аудио'}", CYAN)
        await status_msg.edit_text("1/3. Разделение вокала и инструментала через Demucs...")
        vp, ip = await asyncio.to_thread(split_vocals_instrumental, original_path, DOWNLOADS_DIR)

        voice_title = AVAILABLE_VOICES.get(voice, {}).get("name", voice)
        log_event("RVC", f"Инференс голоса {voice_title} | pitch: {pitch:+d}", MAGENTA)
        await status_msg.edit_text(f"2/3. Преобразование вокала в голос {voice_title}...")
        pvp = await asyncio.to_thread(applio_process_voice, vp, voice, pitch)

        if volume_percent != 100:
            log_event("GAIN", f"Регулировка громкости вокала: {volume_percent}%", YELLOW)
            d, sr = sf.read(pvp)
            sf.write(pvp, np.clip(d * (volume_percent / 100.0), -1.0, 1.0), sr)

        new_title = f"{original_title} ({voice_title} cover)" if original_title else f"{voice_title} cover"
        new_performer = f"{original_performer} feat. Mashuper" if original_performer else "Mashuper"

        log_event("MIX", f"Сведение вокала с оригинальным минусом через FFmpeg", BLUE)
        await status_msg.edit_text("3/3. Сведение вокала с инструменталом...")
        fp = os.path.join(PROCESSED_DIR, f"{uid}_{sid}_final.wav")
        await asyncio.to_thread(merge_vocals_instrumental, pvp, ip, fp)

        await status_msg.edit_text("Готово. Отправка трека...")
        audio_dur = source_message.audio.duration if source_message.audio else None

        await source_message.answer_audio(
            FSInputFile(fp, filename=f"{new_title}.wav"),
            title=new_title,
            performer=new_performer,
            duration=audio_dur
        )
        try:
            await status_msg.delete()
        except Exception:
            pass

        save_message(uid, "out", file_id=fp)
        update_stats(uid, f"{uid}_{sid}_final.wav")
        log_event("READY", f"Финальный трек отправлен: {new_title}", GREEN)

    finally:
        cleanup_files(original_path, vp, ip, pvp, fp)

# хэндлеры команд

@dp.message(Command("start"))
@check_time
@check_blocked
@check_subscription
async def start_handler(message: types.Message, **kwargs): # старт диалога
    uid = message.from_user.id
    add_user(uid, message.from_user.username, message.from_user.first_name)
    save_message(uid, "in", text="/start")
    text = (
        "Привет. Я MashuperBot — нейросеть для создания мешапов и смены голоса.\n\n"
        "Отправь мне аудиофайл (MP3 или WAV) — я отделю вокал, изменю тембр и сведу с оригинальным инструменталом."
    )
    await message.answer(text, reply_markup=get_main_keyboard())
    save_message(uid, "out", text=text)

# переключение голосов пользователем

@dp.message(Command("valakas"))
@check_time
@check_blocked
@check_subscription
async def set_valakas_handler(message: types.Message, **kwargs):
    uid = message.from_user.id
    user_selected_voices[uid] = "valakas"
    save_message(uid, "in", text="/valakas")
    await message.answer(f"Текущий голос переключен на: {AVAILABLE_VOICES['valakas']['name']}")

@dp.message(Command("dora"))
@check_time
@check_blocked
@check_subscription
async def set_dora_handler(message: types.Message, **kwargs):
    uid = message.from_user.id
    user_selected_voices[uid] = "dora"
    save_message(uid, "in", text="/dora")
    await message.answer(f"Текущий голос переключен на: {AVAILABLE_VOICES['dora']['name']}")

@dp.message(F.text == "Библиотека голосов")
@check_time
@check_blocked
@check_subscription
async def open_library_handler(message: types.Message, **kwargs):
    uid = message.from_user.id
    save_message(uid, "in", text="Библиотека голосов")
    await message.answer(build_library_text(uid), parse_mode="HTML")

@dp.message(F.text == "Моя статистика")
@check_time
@check_blocked
@check_subscription
async def show_stats_handler(message: types.Message, **kwargs):
    uid = message.from_user.id
    save_message(uid, "in", text="Моя статистика")
    text = get_user_stats_text(uid, message.from_user.username or "")
    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "check_all_subscriptions")
async def handle_subscribe_check(callback: types.CallbackQuery): # повторная проверка подписок
    uid = callback.from_user.id
    unsub = await get_unsubscribed_channels(bot, uid)
    if not unsub:
        await callback.message.edit_text(
            "Подписка подтверждена. Теперь вам доступен весь функционал бота.\nОтправьте аудиофайл для обработки.",
            reply_markup=None
        )
        await callback.answer("Доступ открыт")
    else:
        ch_list = "\n".join([f"• {name}" for _, _, name in unsub])
        try:
            await callback.message.edit_text(
                f"Вы всё ещё не подписаны на каналы:\n\n{ch_list}\n\nПодпишитесь и нажмите кнопку снова.",
                reply_markup=get_subscription_keyboard(unsub)
            )
        except Exception:
            pass
        await callback.answer("Подписки не найдены", show_alert=True)

# прием и валидация аудио

@dp.message(F.audio | F.document)
@check_time
@check_blocked
@check_subscription
async def handle_audio_message(message: types.Message, state: FSMContext, **kwargs):
    uid = message.from_user.id
    un = message.from_user.username or str(uid)
    add_user(uid, message.from_user.username, message.from_user.first_name)

    # определяем аудио объект (напрямую audio или document с аудио mime-типом)
    audio_obj = message.audio
    is_doc = False
    if not audio_obj and message.document:
        doc = message.document
        ext = os.path.splitext(doc.file_name or "")[1].lower()
        if (doc.mime_type and doc.mime_type.startswith("audio/")) or ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a"]:
            audio_obj = doc
            is_doc = True

    if not audio_obj:
        await message.answer("Пожалуйста, отправьте аудиофайл в формате MP3 или WAV.")
        return

    save_message(uid, "in", file_id=audio_obj.file_id)

    if not can_make_processing(uid):
        await message.answer("Лимит исчерпан: вы уже использовали 3 обработки на сегодня. Завтра попытки обновятся.")
        return

    # проверка длительности если передано audio
    if not is_doc and message.audio and message.audio.duration:
        dur = message.audio.duration
        if dur < 10 and uid not in ADMIN_IDS:
            await message.answer("Аудио слишком короткое (меньше 10 секунд). Отправьте полноценный трек.")
            return
        if dur > 300 and uid not in ADMIN_IDS:
            await message.answer("Аудио слишком длинное (больше 5 минут). Отправьте трек покороче.")
            return

    # проверка веса файла
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if audio_obj.file_size and audio_obj.file_size > max_bytes and uid not in ADMIN_IDS:
        await message.answer(f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE_MB} МБ.")
        return

    try:
        file_info = await bot.get_file(audio_obj.file_id)
        sid = uuid.uuid4().hex[:8]
        ext = os.path.splitext(file_info.file_path or ".mp3")[1] or ".mp3"
        local_path = os.path.join(DOWNLOADS_DIR, f"{uid}_{sid}{ext}")

        await bot.download_file(file_info.file_path, local_path)

        orig_title = getattr(audio_obj, "title", None) or os.path.splitext(getattr(audio_obj, "file_name", "track"))[0]
        orig_perf = getattr(audio_obj, "performer", None) or ""

        await state.set_state(VoiceSelection.waiting_for_gender)
        await state.update_data(
            sid=sid,
            local_path=local_path,
            title=orig_title,
            performer=orig_perf,
        )

        await message.answer("Какой тип голоса преобладает в оригинальной песне?", reply_markup=get_gender_keyboard())
    except Exception as e:
        logger.exception("ошибка сохранения файла от пользователя: %s", e)
        await message.answer("Не удалось загрузить файл из Telegram. Попробуйте еще раз.")

# шаги выбора тембра и громкости

@dp.callback_query(F.data.startswith("gender_"))
async def process_gender_step(callback: types.CallbackQuery, state: FSMContext):
    gender_type = callback.data.split("gender_", 1)[1]
    data = await state.get_data()
    if "local_path" not in data or not os.path.exists(data["local_path"]):
        await callback.message.edit_text("Сессия устарела. Пожалуйста, отправьте аудиофайл заново.")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(gender=gender_type)
    await state.set_state(VoiceSelection.waiting_for_volume)
    await callback.message.edit_text(
        "Выберите желаемую громкость нового вокала относительно музыки:",
        reply_markup=get_volume_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("volume_"))
async def process_volume_step(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    un = callback.from_user.username or str(uid)
    vol = int(callback.data.split("volume_", 1)[1])
    data = await state.get_data()

    if "local_path" not in data or not os.path.exists(data["local_path"]):
        await callback.message.edit_text("Сессия устарела. Отправьте файл заново.")
        await state.clear()
        await callback.answer()
        return

    if not can_make_processing(uid):
        await callback.message.edit_text("Лимит на сегодня исчерпан. Возвращайтесь завтра.")
        await state.clear()
        await callback.answer()
        return

    increment_processing_count(uid, un)

    sid = data["sid"]
    orig_path = data["local_path"]
    title = data["title"]
    perf = data["performer"]
    gender_type = data["gender"]
    await state.clear()

    voice = user_selected_voices.get(uid, "valakas")
    pitch = AVAILABLE_VOICES.get(voice, {}).get("pitch_map", {}).get(gender_type, 0)

    st_msg = await callback.message.edit_text("Файл поставлен в очередь на обработку...")
    await callback.answer()

    async with queue_lock:
        pos = processing_queue.qsize() + (1 if current_task_running else 0)
        queue_positions[sid] = pos
        task_messages[sid] = st_msg

    if pos > 0:
        await st_msg.edit_text(f"Ожидание в очереди... Перед вами задач: {pos}")

    await processing_queue.put((
        sid,
        st_msg,
        orig_path,
        callback.message,
        title,
        perf,
        voice,
        pitch,
        vol
    ))

@dp.message()
@check_time
@check_blocked
@check_subscription
async def catch_all_messages(message: types.Message, **kwargs):
    if not message.text or not message.text.startswith("/"):
        await message.answer("Я обрабатываю музыку. Отправьте мне трек в формате MP3 или WAV.")

# фоновые сервисные задачи

async def cleanup_old_files_task(): # периодическая очистка временных файлов старше 15 минут
    while True:
        await asyncio.sleep(600)
        now = time.time()
        for folder in [DOWNLOADS_DIR, PROCESSED_DIR]:
            if not os.path.exists(folder):
                continue
            for fn in os.listdir(folder):
                fp = os.path.join(folder, fn)
                try:
                    if os.path.isfile(fp) and (now - os.path.getctime(fp) > 900):
                        os.remove(fp)
                except Exception:
                    pass

async def main(): # точка входа и инициализация
    global bot_start_time
    if BOT_TOKEN == "токен_твоего_бота" or not BOT_TOKEN:
        print("ошибка: укажите реальный токен бота в config.py или в переменной BOT_TOKEN")
        return

    bot_start_time = datetime.datetime.now(pytz.UTC)
    init_db()
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    logger.info("Бот MashuperBot успешно инициализирован")

    # запуск фоновых задач
    asyncio.create_task(queue_worker())
    asyncio.create_task(cleanup_old_files_task())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())