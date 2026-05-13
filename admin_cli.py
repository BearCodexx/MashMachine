import os
import json
import asyncio
import sqlite3
import shutil
from datetime import datetime
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from config import *

# пути
DATA_FILE = "data/users.json"
CHAT_DB = "data/chats.db"
STATS_DB = "data/mashuper_stats.db"

# настройка бота с прокси
if PROXY_ENABLED:
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=BOT_TOKEN, session=session)
else:
    bot = Bot(token=BOT_TOKEN)


# база данных статистики

def init_stats_db(): # инициализирует базу данных статистики
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(STATS_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats
                 (
                     user_id
                     INTEGER
                     PRIMARY
                     KEY,
                     username
                     TEXT,
                     total_calls
                     INTEGER
                     DEFAULT
                     0,
                     angry_ends
                     INTEGER
                     DEFAULT
                     0,
                     successful_orders
                     INTEGER
                     DEFAULT
                     0,
                     last_call_date
                     TEXT,
                     calls_today
                     INTEGER
                     DEFAULT
                     0
                 )''')
    conn.commit()
    conn.close()


def get_user_stats(user_id): # получает статистику пользователя
    conn = sqlite3.connect(STATS_DB)
    c = conn.cursor()
    c.execute(
        "SELECT username, total_calls, angry_ends, successful_orders, last_call_date, calls_today FROM user_stats WHERE user_id = ?",
        (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "username": row[0],
            "total_calls": row[1],
            "angry_ends": row[2],
            "successful_orders": row[3],
            "last_call_date": row[4],
            "calls_today": row[5]
        }
    return None


def update_user_stats(user_id, username, field, increment=1): # обновляет статистику пользователя
    conn = sqlite3.connect(STATS_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute(f"UPDATE user_stats SET {field} = {field} + ?, username = ? WHERE user_id = ?",
                  (increment, username, user_id))
    else:
        c.execute(
            "INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, 0, 0, 0, None, 0))
        c.execute(f"UPDATE user_stats SET {field} = {field} + ? WHERE user_id = ?", (increment, user_id))
    conn.commit()
    conn.close()


def increment_calls_total(user_id, username): # увеличивает общий счётчик обработок
    update_user_stats(user_id, username, "total_calls")


def init_stats_db(): # инициализирует базу данных статистики
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/mashuper_stats.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats
                 (
                     user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     total_calls INTEGER DEFAULT 0,
                     angry_ends INTEGER DEFAULT 0,
                     successful_orders INTEGER DEFAULT 0,
                     last_call_date TEXT,
                     calls_today INTEGER DEFAULT 0
                 )''')
    conn.commit()
    conn.close()


def get_user_stats(user_id):
    conn = sqlite3.connect("data/mashuper_stats.db")
    c = conn.cursor()
    c.execute(
        "SELECT username, total_calls, angry_ends, successful_orders, last_call_date, calls_today FROM user_stats WHERE user_id = ?",
        (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "username": row[0],
            "total_calls": row[1],
            "angry_ends": row[2],
            "successful_orders": row[3],
            "last_call_date": row[4],
            "calls_today": row[5]
        }
    return None


def update_user_calls_today(user_id, username, calls_today):
    conn = sqlite3.connect("data/mashuper_stats.db")
    c = conn.cursor()
    c.execute("UPDATE user_stats SET calls_today = ?, username = ? WHERE user_id = ?",
              (calls_today, username, user_id))
    if c.rowcount == 0:
        c.execute(
            "INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 0, 0, 0, ?, ?)",
            (user_id, username, None, calls_today))
    conn.commit()
    conn.close()


def increment_calls_total(user_id, username): # увеличивает общее количество звонков
    conn = sqlite3.connect("data/mashuper_stats.db")
    c = conn.cursor()
    c.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute("UPDATE user_stats SET total_calls = total_calls + 1, username = ? WHERE user_id = ?",
                  (username, user_id))
    else:
        c.execute(
            "INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 1, 0, 0, ?, ?)",
            (user_id, username, None, 0))
    conn.commit()
    conn.close()


# основные функции

def load_data(): # загружает данные пользователей из джейсона
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "blocked": [], "stats": {"total_processed": 0}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data): # сохраняет данные пользователей в джейсон
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def init_chat_db(): # инициализирует базу данных чатов
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(CHAT_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     user_id
                     INTEGER,
                     direction
                     TEXT,
                     message
                     TEXT,
                     file_id
                     TEXT,
                     timestamp
                     DATETIME
                     DEFAULT
                     CURRENT_TIMESTAMP
                 )''')
    conn.commit()
    conn.close()


def add_user(user_id, username, first_name): # добавляет нового пользователя в базу
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "first_seen": datetime.now().isoformat(),
            "last_file": None,
            "files_count": 0
        }
        save_data(data)


def update_stats(user_id, filename): # обновляет статистику обработок
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str in data["users"]:
        data["users"][user_id_str]["last_file"] = filename
        data["users"][user_id_str]["files_count"] += 1
    data["stats"]["total_processed"] += 1
    save_data(data)


def is_blocked(user_id): # чек блокировки
    data = load_data()
    return str(user_id) in data["blocked"]


def block_user(user_id): # блокируем
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str not in data["blocked"]:
        data["blocked"].append(user_id_str)
        save_data(data)
        return True
    return False


def unblock_user(user_id): # разбан
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str in data["blocked"]:
        data["blocked"].remove(user_id_str)
        save_data(data)
        return True
    return False


def save_message(user_id, direction, text=None, file_id=None): # сохранение в историю
    conn = sqlite3.connect(CHAT_DB)
    c = conn.cursor()
    c.execute("INSERT INTO messages (user_id, direction, message, file_id) VALUES (?, ?, ?, ?)",
              (user_id, direction, text, file_id))
    conn.commit()
    # ограничиваем 30 сообщениями
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,))
    count = c.fetchone()[0]
    if count > 30:
        c.execute("SELECT id FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?", (user_id, count - 30))
        old_ids = [row[0] for row in c.fetchall()]
        if old_ids:
            placeholders = ",".join("?" for _ in old_ids)
            c.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", old_ids)
            conn.commit()
    conn.close()


def get_chat_history(user_id, limit=100): # возвращаем историю чата с пользователем
    conn = sqlite3.connect(CHAT_DB)
    c = conn.cursor()
    c.execute("SELECT direction, message, file_id, timestamp FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows[::-1]


def show_users(): # список всех юзеров
    data = load_data()
    users = data["users"]
    if not users:
        print("Нет пользователей")
        return
    print(f"\nВСЕ ПОЛЬЗОВАТЕЛИ ({len(users)}):")
    print("-" * 60)
    for uid, info in users.items():
        blocked = "🔒" if uid in data["blocked"] else "✅"
        is_admin = "👑" if int(uid) in ADMIN_IDS else "  "
        stats = get_user_stats(int(uid))
        if stats:
            processed_today = stats["calls_today"] if stats[
                                                          "last_call_date"] == datetime.date.today().isoformat() else 0
            total_calls = stats["total_calls"]
        else:
            processed_today = 0
            total_calls = info.get("files_count", 0)

        # выводим с никнеймом и ID
        username_display = f"@{info['username']}" if info['username'] else "без ника"
        print(f"{blocked} {is_admin} {info['first_name']} ({username_display})")
        print(f"   ID: {uid}")
        print(f"   Обработок сегодня: {processed_today}/3, Всего: {total_calls}")
        print(f"   Впервые: {info['first_seen']}")
        print()


def show_stats(): # показываем общую стату
    data = load_data()
    conn = sqlite3.connect(STATS_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_stats")
    users_with_stats = c.fetchone()[0]
    conn.close()

    print("\nСТАТИСТИКА:")
    print(f"   Всего пользователей: {len(data['users'])}")
    print(f"   Заблокировано: {len(data['blocked'])}")
    print(f"   Обработано файлов: {data['stats']['total_processed']}")
    print(f"   Пользователей со статистикой: {users_with_stats}")
    print()


def show_blocked(): # показывает список заблокированных пользователей
    data = load_data()
    blocked = data["blocked"]
    if not blocked:
        print("Нет заблокированных пользователей")
        return
    print(f"\nЗАБЛОКИРОВАННЫЕ ({len(blocked)}):")
    for uid in blocked:
        user = data["users"].get(uid, {})
        name = user.get("first_name", "Неизвестно")
        username = user.get("username", "")
        print(f"   {name} (@{username}) — ID: {uid}")


def show_chat(user_id): # показывает диалог с пользователем
    rows = get_chat_history(user_id)
    if not rows:
        print("Нет сообщений с этим пользователем")
        return
    data = load_data()
    user = data["users"].get(str(user_id), {})
    name = user.get("first_name", "Неизвестно")
    print(f"\nДИАЛОГ С {name} (ID: {user_id}):")
    print("=" * 60)
    for direction, text, file_id, ts in rows:
        time_str = ts[:19] if ts else "неизвестно"
        if direction == "in":
            print(f"[{time_str}] 👤 ПОЛЬЗОВАТЕЛЬ:")
        else:
            print(f"[{time_str}] 🤖 БОТ:")
        if text:
            print(f"   {text}")
        if file_id:
            print(f"   📎 ФАЙЛ (file_id: {file_id})")
        print()


async def send_message(user_id, text): # отправляет сообщение пользователю
    try:
        await bot.send_message(user_id, text)
        print(f"Сообщение отправлено пользователю {user_id}")
        save_message(user_id, "out", text=f"[ADMIN] {text}")
    except Exception as e:
        print(f"Ошибка: {e}")


async def broadcast(text): # делает рассылку всем юзерам
    data = load_data()
    success = 0
    fail = 0
    for uid, info in data["users"].items():
        if uid not in data["blocked"]:
            try:
                await bot.send_message(int(uid), f"{text}", parse_mode="Markdown")
                success += 1
                save_message(int(uid), "out", text=f"[BROADCAST] {text}")
            except:
                fail += 1
    print(f"Отправлено: {success}, Ошибок: {fail}")


def download_user_file(user_id): # скачивает последний файл юзера
    data = load_data()
    user = data["users"].get(str(user_id))
    if not user or not user.get("last_file"):
        print("У пользователя нет сохранённых файлов")
        return
    filename = user["last_file"]
    filepath = os.path.join(PROCESSED_DIR, filename)
    if os.path.exists(filepath):
        shutil.copy(filepath, f"{user['first_name']}_{filename}")
        print(f"Скопирован как {user['first_name']}_{filename}")
    else:
        print("Файл не найден на диске")


def show_help(): # показывает справку по командам
    print("""
╔══════════════════════════════════════════════════════════╗
║              АДМИН-ПАНЕЛЬ MashMachine                    ║
╠══════════════════════════════════════════════════════════╣
║  users             — список всех пользователей           ║
║  stats             — статистика                          ║
║  blocked           — список заблокированных              ║
║  block <id>        — заблокировать пользователя          ║
║  unblock <id>      — разблокировать                      ║
║  chat <id>         — показать диалог с пользователем     ║
║  msg <id> <текст>  — отправить сообщение                 ║
║  broadcast <текст> — рассылка всем                       ║
║  file <id>         — скачать последний файл пользователя ║
║  help              — справка                             ║
║  exit / quit       — выход                               ║
╚══════════════════════════════════════════════════════════╝
""")


async def main(): # мейн функция админ панели
    init_chat_db()
    init_stats_db()
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DATA_FILE):
        save_data({"users": {}, "blocked": [], "stats": {"total_processed": 0}})

    print("\n🔐 АДМИН-ПАНЕЛЬ MashMachine")
    print("Введите help для списка команд\n")
    while True:
        cmd = input("admin> ").strip()
        if not cmd:
            continue
        parts = cmd.split()
        command = parts[0].lower()

        if command in ["exit", "quit"]:
            print("Выход...")
            break
        elif command == "help":
            show_help()
        elif command == "users":
            show_users()
        elif command == "stats":
            show_stats()
        elif command == "blocked":
            show_blocked()
        elif command == "block" and len(parts) > 1:
            if block_user(parts[1]):
                print(f"Пользователь {parts[1]} заблокирован")
            else:
                print(f"Пользователь {parts[1]} уже был заблокирован")
        elif command == "unblock" and len(parts) > 1:
            if unblock_user(parts[1]):
                print(f"Пользователь {parts[1]} разблокирован")
            else:
                print(f"Пользователь {parts[1]} не был заблокирован")
        elif command == "chat" and len(parts) > 1:
            show_chat(parts[1])
        elif command == "msg" and len(parts) > 2:
            await send_message(parts[1], " ".join(parts[2:]))
        elif command == "broadcast" and len(parts) > 1:
            await broadcast(" ".join(parts[1:]))
        elif command == "file" and len(parts) > 1:
            download_user_file(parts[1])
        else:
            print("Неизвестная команда. Введите help")

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())