import logging, os, time, shutil, uuid, asyncio, datetime, pytz, sqlite3, re
import numpy as np
import soundfile as sf
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from config import *
from utils.demucs_split import \
    split_vocals_instrumental  # это разделение аудио на дорожки через demucs (demucs_split.py)
from utils.rvc_applio import \
    applio_process_voice  # инференс апплио на уровне сервиса (должен быть открыт в 127.0.0.1:6969) (rvc_applio.py)
from utils.audio_merge import merge_vocals_instrumental  # склейка меш голоса и инструментала (audio_merge.py)
from utils.cleanup import cleanup_files  # почистить все после отправки (cleanup.py)

# импорты для администрирования
from admin_cli import add_user, update_stats, is_blocked, save_message, get_chat_history, init_stats_db, get_user_stats, \
    update_user_calls_today, increment_calls_total

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# настройка бота с прокси
session = AiohttpSession(proxy=PROXY_URL) if PROXY_ENABLED else None
bot = Bot(token=BOT_TOKEN, session=session) if PROXY_ENABLED else Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
bot_start_time = datetime.datetime.now(datetime.timezone.utc)


# ниже проверка на наличие подписки на тгк
async def is_subscribed(bot_instance, user_id: int) -> bool:
    for channel_id, _, _ in REQUIRED_CHANNELS:
        try:
            cid = int(channel_id) if not channel_id.startswith('@') else channel_id
            if (await bot_instance.get_chat_member(chat_id=cid, user_id=user_id)).status not in ["member", "creator", "administrator", "restricted"]: return False
        except: return False
    return True


def get_subscription_keyboard(unsubscribed_channels: list) -> InlineKeyboardMarkup: # клавы с кнопками на каждый тгк
    kb = [[InlineKeyboardButton(text=f"Подписаться на {n}", url=u)] for _, u, n in unsubscribed_channels]
    kb.append([InlineKeyboardButton(text="Проверить подписки", callback_data="check_all_subscriptions")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def get_unsubscribed_channels(bot_instance, user_id: int) -> list: # возвращаем тгк на которые юзер не подписан
    unsub = []
    for channel_id, channel_url, channel_name in REQUIRED_CHANNELS:
        try:
            cid = int(channel_id) if not channel_id.startswith('@') else channel_id
            if (await bot_instance.get_chat_member(chat_id=cid, user_id=user_id)).status not in ["member", "creator", "administrator", "restricted"]: unsub.append((channel_id, channel_url, channel_name))
        except: unsub.append((channel_id, channel_url, channel_name))
    return unsub


# декораторы

# декоратор для проверки времени сообщения (отсекает офлайн сообщения)
def check_time(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        global bot_start_time
        msg_time = message.date.replace(tzinfo=datetime.timezone.utc) if message.date.tzinfo is None else message.date
        if msg_time < bot_start_time: return
        return await func(message, *args, **kwargs)
    return wrapper


# декоратор для проверки на статус блока
def check_blocked(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        if is_blocked(message.from_user.id): await message.answer("Вы заблокированы."); return
        return await func(message, *args, **kwargs)
    return wrapper


# декоратор для проверки подписки на каналы
def check_subscription(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        uid = message.from_user.id
        if not REQUIRED_CHANNELS: return await func(message, *args, **kwargs)
        unsub = await get_unsubscribed_channels(bot, uid)
        if not unsub: return await func(message, *args, **kwargs)
        ch_list = "\n".join([f"• {name} — {cid}" for cid, _, name in unsub])
        await message.answer(f"Доступ ограничен\n\nДля использования бота необходимо подписаться на следующие каналы:\n\n{ch_list}\n\nПосле подписки нажмите «Проверить подписки»", reply_markup=get_subscription_keyboard(unsub))
    return wrapper


# функции статистики

def can_make_processing(user_id): # проверяет, может ли пользователь обработать аудио сегодня
    if user_id in ADMIN_IDS: return True
    stats = get_user_stats(user_id)
    today = datetime.date.today().isoformat()
    return True if not stats or stats["last_call_date"] != today else stats["calls_today"] < 3


def increment_processing_count(user_id, username):
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect("data/mashuper_stats.db"); c = conn.cursor()
    if user_id in ADMIN_IDS:
        if c.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,)).fetchone(): c.execute("UPDATE user_stats SET total_calls = total_calls + 1, username = ? WHERE user_id = ?", (username, user_id))
        else: c.execute("INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 1, 0, 0, ?, ?)", (user_id, username, today, 0))
    else:
        stats = get_user_stats(user_id)
        calls_today = 1 if not stats or stats["last_call_date"] != today else stats["calls_today"] + 1
        c.execute("UPDATE user_stats SET calls_today = ?, last_call_date = ?, username = ? WHERE user_id = ?", (calls_today, today, username, user_id))
        if c.rowcount == 0: c.execute("INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 0, 0, 0, ?, ?)", (user_id, username, today, calls_today))
        else: c.execute("UPDATE user_stats SET total_calls = total_calls + 1 WHERE user_id = ?", (user_id,))
    conn.commit(); conn.close()


def get_user_stats_text(user_id, username):
    stats = get_user_stats(user_id)
    if not stats: return "Статистика пока не накоплена"
    today = datetime.date.today().isoformat()
    calls_today = 0 if stats["last_call_date"] != today else stats["calls_today"]
    available = "∞ (админ)" if user_id in ADMIN_IDS else f"{max(0, 3 - calls_today)}/3"
    voice_name = AVAILABLE_VOICES.get(current_voice, {}).get("name", "Валакас")
    display_name = username.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]')
    return f"*Ваша статистика*\n\n*Ник:* @{display_name}\n*ID:* `{user_id}`\n*Текущий голос:* {voice_name}\n*Доступно обработок сегодня:* {available}\n*Всего обработок:* {stats['total_calls']}\n"


# cостояния FSM (машина состояний). в aiogram это надо, чтобы бот знал, на каком этапе диалога находится и чего ждать от юзера
class VoiceSelection(StatesGroup):
    waiting_for_gender = State()  # ждем выбор типа голоса (мужской или женский)
    waiting_for_volume = State()  # ждем выбор громкости (НОВОЕ)


# голоса (это можно расширять потом). пич мап - это сетка тембров относительно 0 (тембра на обучении)
AVAILABLE_VOICES = {
    "valakas": {
        "name": "Валакас", "lang": "Русский", "gender": "Мужской (грубый)",
        "pitch_map": {"Грубый мужской": -18, "Мужской": -20, "Грубый женский": -21, "Женский": -24}
        # у Валакаса слишком мягкий на нуле даже если исполнитель - басистый дед
    },
    "dora": {
        "name": "Дора", "lang": "Русский", "gender": "Женский (молодой)",
        "pitch_map": {"Грубый мужской": 5, "Мужской": 3, "Грубый женский": 3, "Женский": 0}
    }
}
current_voice = "valakas"  # по умолчанию Валакас, потом сделаю обязательный выбор

# хранилища для очереди и временных данных, а еще флаг (есть ли обработка) и блокировка для доступа к очереди
user_pending, processing_queue, queue_positions, task_messages = {}, asyncio.Queue(), {}, {}
is_processing, queue_lock = False, asyncio.Lock()


# клавиатуры для выбора типа голоса (инлайн)
def get_gender_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=f"gender_{t}")] for t in
        ["Грубый мужской", "Мужской", "Грубый женский", "Женский"]
    ])


def get_volume_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50%", callback_data="volume_50"),
         InlineKeyboardButton(text="75%", callback_data="volume_75"),
         InlineKeyboardButton(text="100%", callback_data="volume_100")],
        [InlineKeyboardButton(text="125%", callback_data="volume_125"),
         InlineKeyboardButton(text="150%", callback_data="volume_150"),
         InlineKeyboardButton(text="200%", callback_data="volume_200")]
    ])


# основная клавиатура (репли, в меню)
def get_main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Библиотека голосов"), KeyboardButton(text="Моя статистика")]
    ], resize_keyboard=True)


# формируем текст для библиотеки голосов (лучше так, чем потом для 100500 голосов отдельно прописывать)
def build_library_text():
    return "🎵 *Библиотека голосов*\n\n" + "\n".join(
        f"• *{v['name']}* — {v['lang']}, {v['gender']}\n  /{k} — выбрать этот голос"
        for k, v in AVAILABLE_VOICES.items()
    )


# обновляет сообщения о позиции в очереди
async def update_all_queue_positions():
    async with queue_lock:
        for uid, pos in queue_positions.items():
            if uid in task_messages and pos and pos > 0:
                await task_messages[uid].edit_text(f"Обрабатываю вокал ({current_voice})...\n\nОчередь: {pos} перед вами")


# запускает следующую задачу из очереди (всю эту функцию разбирайте с гпт опенаишным, глобал очередь в основном он писал)
async def process_next_in_queue():
    global is_processing
    if processing_queue.empty(): is_processing = False; return
    is_processing = True
    uid, original_path, message, original_title, original_performer, voice, pitch, volume_percent = await processing_queue.get()
    status_msg = task_messages.get(uid)
    # дальше обновляем позиции оставшихся
    async with queue_lock:
        for u in list(queue_positions.keys()):
            if u != uid and queue_positions[u] and queue_positions[u] > 0: queue_positions[u] -= 1
        queue_positions.pop(uid, None); task_messages.pop(uid, None)
    await update_all_queue_positions()
    # запускаем обработку (функция идет ниже следующей)
    await process_audio_task(uid, status_msg, original_path, message, original_title, original_performer, voice, pitch, volume_percent)
    asyncio.create_task(process_next_in_queue())  # рекурсивный вызов для следующей задачи


# вот она, обработка. обращаемся ко всем скриптам с utils (разделение, RVC, склейка), выводим статус юзеру
async def process_audio_task(uid, status_msg, original_path, message, original_title, original_performer, voice, pitch, volume_percent=100):
    vp = ip = pvp = fp = None
    try:
        await status_msg.edit_text("Разделяю вокал и инструментал...")
        vp, ip = await asyncio.to_thread(split_vocals_instrumental, original_path, DOWNLOADS_DIR)
        await status_msg.edit_text(f"Обрабатываю вокал ({voice})...")
        pvp = await asyncio.to_thread(applio_process_voice, vp, voice, pitch)
        if volume_percent != 100:
            await status_msg.edit_text(f"Регулирую громкость ({volume_percent}%)...")
            d, sr = sf.read(pvp); sf.write(pvp, np.clip(d * (volume_percent / 100.0), -1.0, 1.0), sr)
        await status_msg.edit_text("Склеиваю вокал с инструменталом...")
        fp = os.path.join(PROCESSED_DIR, f"{uid}_final.wav")
        await asyncio.to_thread(merge_vocals_instrumental, pvp, ip, fp)
        new_title = f"{original_title} ({voice} remix)" if original_title else f"{voice} hit"
        new_performer = f"{original_performer} ft. MashMachine" if original_performer else "MashMachine"
        await status_msg.edit_text("Готово! Отправляю результат...")
        await message.answer_audio(FSInputFile(fp, filename=f"{uid}_final.wav"), title=new_title, performer=new_performer, duration=message.audio.duration)
        await status_msg.delete()
        save_message(message.from_user.id, "out", file_id=fp)
        update_stats(message.from_user.id, f"{uid}_final.wav")
    except Exception as e:
        logger.exception("Ошибка обработки")
        await status_msg.edit_text(f"Ошибка: {str(e)}")
    finally:
        cleanup_files(*[p for p in [original_path, vp, ip, pvp, fp] if p and os.path.exists(p)])


# хендлеры команд с декораторами

@dp.message(Command("start"))  # приветствие при запуске
@check_time
@check_blocked
@check_subscription
async def start(message: types.Message, **kwargs): # обработчик команды start
    uid = message.from_user.id
    add_user(uid, message.from_user.username, message.from_user.first_name); init_stats_db()
    save_message(uid, "in", text="/start")
    await message.answer("Привет! Я - Меш-машина, создаю мешапы на базе технологии RVC.\nОтправь мне MP3 или WAV - я обработаю вокал и верну ваш нейромешап.\n\n", reply_markup=get_main_keyboard())
    save_message(uid, "out", text="Привет! Я - Меш-машина, создаю мешапы на базе технологии RVC.\nОтправь мне MP3 или WAV - я обработаю вокал и верну ваш нейромешап.")


@dp.message(Command("valakas"))  # переключаем на Валакаса
@check_time
@check_blocked
@check_subscription
async def set_valakas(message: types.Message, **kwargs):
    global current_voice
    uid = message.from_user.id; save_message(uid, "in", text="/valakas")
    current_voice = "valakas"
    await message.answer(f"Голос сменён на {AVAILABLE_VOICES['valakas']['name']}")
    save_message(uid, "out", text=f"Голос сменён на {AVAILABLE_VOICES['valakas']['name']}")


@dp.message(Command("dora"))  # переключаем на Дору
@check_time
@check_blocked
@check_subscription
async def set_dora(message: types.Message, **kwargs):
    global current_voice
    uid = message.from_user.id; save_message(uid, "in", text="/dora")
    current_voice = "dora"
    await message.answer(f"Голос сменён на {AVAILABLE_VOICES['dora']['name']}")
    save_message(uid, "out", text=f"Голос сменён на {AVAILABLE_VOICES['dora']['name']}")


@dp.message(lambda m: m.text == "Библиотека голосов")  # библиотека через репли кнопку
@check_time
@check_blocked
@check_subscription
async def open_library(message: types.Message, **kwargs):
    uid = message.from_user.id; save_message(uid, "in", text="Библиотека голосов")
    await message.answer(build_library_text(), parse_mode="Markdown")
    save_message(uid, "out", text=build_library_text())


@dp.message(lambda m: m.text == "Моя статистика")
@check_time
@check_blocked
@check_subscription
async def show_my_stats(message: types.Message, **kwargs): # показывает статистику юзера
    uid = message.from_user.id; un = message.from_user.username or str(uid)
    t = get_user_stats_text(uid, un); await message.answer(t, parse_mode="Markdown")
    save_message(uid, "out", text=t)


@dp.callback_query(lambda c: c.data == "library")
async def show_library(callback: types.CallbackQuery): # обработчик кнопки библиотеки голосов в инлайн режиме
    uid = callback.from_user.id; save_message(uid, "in", text="library callback")
    await callback.message.edit_text(build_library_text(), parse_mode="Markdown"); await callback.answer()
    save_message(uid, "out", text=build_library_text())


# хендлер для проверки подписки

@dp.callback_query(lambda c: c.data == "check_all_subscriptions") # обработчик кнопки для подписки на тгк
async def handle_subscribe_check(callback: types.CallbackQuery):
    uid = callback.from_user.id
    unsub = await get_unsubscribed_channels(bot, uid)
    if not unsub:
        await callback.message.edit_text("Спасибо за подписки! Теперь вам доступен весь функционал бота.\n\nПовторите ваш запрос", reply_markup=None)
        await callback.answer("Доступ открыт. Повторите запрос.", show_alert=True)
    else:
        ch_list = "\n".join([f"• {n}" for _, _, n in unsub])
        try: await callback.message.edit_text(f"Вы всё ещё не подписаны на:\n\n{ch_list}\n\nПодпишитесь и нажмите «Проверить подписки» снова", reply_markup=get_subscription_keyboard(unsub))
        except: await callback.answer("Вы всё ещё не подписались на каналы.", show_alert=True)


# аудио хендлер

# ниже прием аудио, сохранение и переход в состояние выбора голоса
@dp.message(lambda msg: msg.audio)
@check_time
@check_blocked
@check_subscription
async def handle_audio(message: types.Message, state: FSMContext, **kwargs):
    uid = message.from_user.id; un = message.from_user.username or str(uid)
    add_user(uid, message.from_user.username, message.from_user.first_name)
    save_message(uid, "in", file_id=message.audio.file_id)
    if is_blocked(uid): await message.answer("Вы заблокированы администратором."); return
    if not can_make_processing(uid): await message.answer("Сегодня вы уже использовали все 3 обработки. Завтра будут новые!"); return
    dur = message.audio.duration
    if dur:
        if dur < 15 and uid not in ADMIN_IDS: await message.answer("Аудио слишком короткое (меньше 15 секунд). Отправьте более длинный файл."); return
        if dur > 240 and uid not in ADMIN_IDS: await message.answer("Аудио слишком длинное (больше 4 минут). Отправьте более короткий файл."); return
    if uid not in ADMIN_IDS and message.audio.file_size > 5 * 1024 * 1024: await message.answer("🎵 Файл слишком большой (больше 5 МБ). Пожалуйста, отправьте файл меньшего размера."); return
    try:
        audio = message.audio; file = await bot.get_file(audio.file_id)
        uid_short = str(uuid.uuid4())[:8]; op = os.path.join(DOWNLOADS_DIR, f"{uid_short}_original.mp3")
        await bot.download_file(file.file_path, op)
        user_pending[uid_short] = (message, op, audio.title, audio.performer)
        await state.set_state(VoiceSelection.waiting_for_gender); await state.update_data(uid=uid_short)
        await message.answer("Какой голос лидирует в песне?", reply_markup=get_gender_keyboard())
        save_message(uid, "out", text="Какой голос лидирует в песне?")
    except: logger.exception("Ошибка в handle_audio"); await message.answer("Не удалось обработать файл. Попробуй ещё раз.")


# обрабатываем тип голоса и переходим к выбору громкости
@dp.callback_query(lambda c: c.data and c.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id; g = callback.data.split("_", 1)[1]
    save_message(uid, "in", text=g)
    data = await state.get_data(); sid = data.get("uid")
    if not sid or sid not in user_pending: await callback.message.edit_text("Сессия устарела. Отправьте файл заново."); await state.clear(); await callback.answer(); return
    await state.update_data(gender=g, uid=sid)
    await callback.message.edit_text("Выберите громкость обработанного вокала относительно исходного:", reply_markup=get_volume_keyboard())
    await callback.answer(); await state.set_state(VoiceSelection.waiting_for_volume)


# обрабатываем выбор громкости и добавляем в очередь
@dp.callback_query(lambda c: c.data and c.data.startswith("volume_"))
async def process_volume(callback: types.CallbackQuery, state: FSMContext):
    global is_processing
    uid = callback.from_user.id; un = callback.from_user.username or str(uid)
    vp = int(callback.data.split("_")[1]); save_message(uid, "in", text=f"Громкость {vp}%")
    data = await state.get_data(); sid = data.get("uid"); g = data.get("gender")
    if not sid or sid not in user_pending: await callback.message.edit_text("Сессия устарела. Отправьте файл заново."); await state.clear(); await callback.answer(); return
    msg, op, ot, opf = user_pending.pop(sid); await state.clear()
    if not can_make_processing(uid): await callback.message.edit_text("Сегодня вы уже использовали все 3 обработки. Завтра будут новые!"); await callback.answer(); return
    increment_processing_count(uid, un)
    voice = current_voice; pitch = AVAILABLE_VOICES[voice]["pitch_map"].get(g, 0)
    st = await callback.message.edit_text("Файл получен. Начинаю обработку..."); await callback.answer()
    save_message(uid, "out", text="Файл получен. Начинаю обработку...")
    async with queue_lock:
        pos = None if not is_processing else processing_queue.qsize() + 1
        queue_positions[sid] = pos; task_messages[sid] = st
    qt = f"Обрабатываю вокал через RVC ({voice})..." + (f"\n\nОчередь: {pos} перед вами" if pos else "")
    await st.edit_text(qt); save_message(uid, "out", text=qt)
    await processing_queue.put((sid, op, msg, ot, opf, voice, pitch, vp))
    if not is_processing: asyncio.create_task(process_next_in_queue())


# общий хендлер, который ловит всё, что не обработано выше
@dp.message()
@check_time
@check_blocked
@check_subscription
async def catch_all_messages(message: types.Message, **kwargs):
    uid = message.from_user.id; txt = message.text or "медиафайл"; save_message(uid, "in", text=txt)
    if not message.text or not message.text.startswith('/'): await message.answer("Я обрабатываю только аудиофайлы. Отправьте мне MP3 или WAV.")


# фоновые задачи
# ниже мы удаляем из папки downloads файлы, созданные больше 10 минут назад
async def cleanup_old_files():
    while True:
        await asyncio.sleep(600)
        try:
            now = time.time()
            for fn in os.listdir(DOWNLOADS_DIR):
                fp = os.path.join(DOWNLOADS_DIR, fn)
                if os.path.isfile(fp) and now - os.path.getctime(fp) > 600: os.remove(fp)
        except Exception as e: logger.error(f"Ошибка при очистке: {e}")


async def main(): # запуск бота
    global bot_start_time
    bot_start_time = datetime.datetime.now(pytz.UTC)
    init_stats_db()
    print(f"Бот запущен в {bot_start_time}")
    asyncio.create_task(cleanup_old_files())
    await dp.start_polling(bot)


if __name__ == "__main__": # ну это база
    asyncio.run(main())