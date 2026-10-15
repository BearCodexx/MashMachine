import os
import sqlite3
import shutil
import asyncio
from datetime import datetime, date
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from config import BASE_DIR, DATA_DIR, PROCESSED_DIR, BOT_TOKEN, PROXY_ENABLED, PROXY_URL, ADMIN_IDS

DB_PATH = os.path.join(DATA_DIR, "mashuper.db")
_admin_bot = None

def get_admin_bot(): # создаем бота только при реальной отправке сообщений из админки
    global _admin_bot
    if _admin_bot is None:
        session = AiohttpSession(proxy=PROXY_URL) if PROXY_ENABLED else None
        _admin_bot = Bot(token=BOT_TOKEN, session=session)
    return _admin_bot

def get_db(): # соединение с базой данных
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(): # инициализация единой схемы базы данных
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            first_seen TEXT,
            last_file TEXT,
            files_count INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            total_calls INTEGER DEFAULT 0,
            angry_ends INTEGER DEFAULT 0,
            successful_orders INTEGER DEFAULT 0,
            last_call_date TEXT,
            calls_today INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            direction TEXT,
            message TEXT,
            file_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

def init_stats_db(): # обратная совместимость вызова инициализации
    init_db()

def init_chat_db(): # обратная совместимость вызова чата
    init_db()

def add_user(user_id, username, first_name): # регистрация или обновление пользователя
    init_db()
    now_iso = datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, first_seen, files_count, is_blocked) VALUES (?, ?, ?, ?, 0, 0)",
                (user_id, username or "", first_name or "", now_iso)
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                (username or "", first_name or "", user_id)
            )

def update_stats(user_id, filename): # обновление счетчика обработанных файлов
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET last_file = ?, files_count = files_count + 1 WHERE user_id = ?",
            (filename, user_id)
        )

def is_blocked(user_id): # проверка пользователя на бан
    with get_db() as conn:
        row = conn.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row["is_blocked"]) if row else False

def block_user(user_id): # блокировка пользователя
    with get_db() as conn:
        res = conn.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (int(user_id),))
        return res.rowcount > 0

def unblock_user(user_id): # разбан пользователя
    with get_db() as conn:
        res = conn.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (int(user_id),))
        return res.rowcount > 0

def save_message(user_id, direction, text=None, file_id=None): # сохранение сообщения и удержание лимита в 30 записей
    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, direction, message, file_id) VALUES (?, ?, ?, ?)",
            (user_id, direction, text, file_id)
        )
        count = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)).fetchone()[0]
        if count > 30:
            conn.execute("""
            DELETE FROM messages WHERE id IN (
                SELECT id FROM messages WHERE user_id = ? ORDER BY id ASC LIMIT ?
            )
            """, (user_id, count - 30))

def get_chat_history(user_id, limit=100): # получение истории переписки
    with get_db() as conn:
        rows = conn.execute(
            "SELECT direction, message, file_id, timestamp FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(r) for r in reversed(rows)]

def get_user_stats(user_id): # получение персональной статистики
    with get_db() as conn:
        row = conn.execute(
            "SELECT username, total_calls, angry_ends, successful_orders, last_call_date, calls_today FROM user_stats WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if row:
            return {
                "username": row["username"],
                "total_calls": row["total_calls"],
                "angry_ends": row["angry_ends"],
                "successful_orders": row["successful_orders"],
                "last_call_date": row["last_call_date"],
                "calls_today": row["calls_today"]
            }
        return None

def update_user_calls_today(user_id, username, calls_today): # установка числа генераций за сегодня
    today = date.today().isoformat()
    with get_db() as conn:
        res = conn.execute(
            "UPDATE user_stats SET calls_today = ?, last_call_date = ?, username = ? WHERE user_id = ?",
            (calls_today, today, username, user_id)
        )
        if res.rowcount == 0:
            conn.execute(
                "INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 0, 0, 0, ?, ?)",
                (user_id, username, today, calls_today)
            )

def increment_calls_total(user_id, username): # инкремент общего счетчика генераций
    today = date.today().isoformat()
    with get_db() as conn:
        res = conn.execute(
            "UPDATE user_stats SET total_calls = total_calls + 1, username = ? WHERE user_id = ?",
            (username, user_id)
        )
        if res.rowcount == 0:
            conn.execute(
                "INSERT INTO user_stats (user_id, username, total_calls, angry_ends, successful_orders, last_call_date, calls_today) VALUES (?, ?, 1, 0, 0, ?, 0)",
                (user_id, username, today)
            )

def show_users(): # вывод списка пользователей в консоль
    init_db()
    with get_db() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY user_id DESC").fetchall()
        if not users:
            print("нет пользователей")
            return

        today = date.today().isoformat()
        print(f"\nВСЕ ПОЛЬЗОВАТЕЛИ ({len(users)}):")
        print("-" * 60)
        for u in users:
            uid = u["user_id"]
            blocked = "[X]" if u["is_blocked"] else "[OK]"
            is_admin = "[A]" if uid in ADMIN_IDS else "   "
            stats = get_user_stats(uid)
            today_calls = stats["calls_today"] if stats and stats["last_call_date"] == today else 0
            total_calls = stats["total_calls"] if stats else u["files_count"]
            uname = f"@{u['username']}" if u['username'] else "без ника"
            print(f"{blocked} {is_admin} {u['first_name']} ({uname})")
            print(f"   ID: {uid}")
            print(f"   Обработок сегодня: {today_calls}/3, Всего: {total_calls}")
            print(f"   Впервые: {u['first_seen']}")
            print()

def show_stats(): # вывод общей сводки
    init_db()
    with get_db() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        blocked_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1").fetchone()[0]
        total_files = conn.execute("SELECT COALESCE(SUM(files_count), 0) FROM users").fetchone()[0]
        total_calls = conn.execute("SELECT COALESCE(SUM(total_calls), 0) FROM user_stats").fetchone()[0]

        print("\nОБЩАЯ СТАТИСТИКА:")
        print(f"   Всего пользователей: {total_users}")
        print(f"   Заблокировано: {blocked_users}")
        print(f"   Успешно обработано файлов: {total_files}")
        print(f"   Суммарных вызовов инференса: {total_calls}\n")

def show_blocked(): # вывод заблокированных пользователей
    init_db()
    with get_db() as conn:
        rows = conn.execute("SELECT user_id, username, first_name FROM users WHERE is_blocked = 1").fetchall()
        if not rows:
            print("нет заблокированных пользователей")
            return
        print(f"\nЗАБЛОКИРОВАННЫЕ ({len(rows)}):")
        for r in rows:
            uname = f"@{r['username']}" if r['username'] else "без ника"
            print(f"   {r['first_name']} ({uname}) — ID: {r['user_id']}")

def show_chat(user_id): # вывод истории диалога
    init_db()
    rows = get_chat_history(user_id)
    if not rows:
        print("нет сообщений с этим пользователем")
        return
    print(f"\nДИАЛОГ С ID: {user_id}:")
    print("=" * 60)
    for direction, text, file_id, ts in rows:
        sender = "ПОЛЬЗОВАТЕЛЬ" if direction == "in" else "БОТ"
        time_str = ts[:19] if ts else "неизвестно"
        print(f"[{time_str}] {sender}:")
        if text:
            print(f"   {text}")
        if file_id:
            print(f"   [файл: {file_id}]")
        print()

async def send_message(user_id, text): # прямая отправка сообщения пользователю
    bot = get_admin_bot()
    try:
        await bot.send_message(user_id, text)
        print(f"сообщение отправлено пользователю {user_id}")
        save_message(user_id, "out", text=f"[ADMIN] {text}")
    except Exception as e:
        print(f"ошибка отправки: {e}")

async def broadcast(text): # массовая рассылка по активным пользователям
    init_db()
    bot = get_admin_bot()
    success, fail = 0, 0
    with get_db() as conn:
        users = conn.execute("SELECT user_id FROM users WHERE is_blocked = 0").fetchall()
    for u in users:
        uid = u["user_id"]
        try:
            await bot.send_message(uid, text)
            success += 1
            save_message(uid, "out", text=f"[BROADCAST] {text}")
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    print(f"рассылка завершена: успешно {success}, ошибок {fail}")

def download_user_file(user_id): # копирование последнего сгенерированного файла
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT first_name, last_file FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row or not row["last_file"]:
        print("у пользователя нет сохраненных файлов")
        return
    filename = row["last_file"]
    filepath = os.path.join(PROCESSED_DIR, filename)
    if os.path.exists(filepath):
        safe_name = row["first_name"].replace(" ", "_") if row["first_name"] else "user"
        target_name = f"{safe_name}_{filename}"
        shutil.copy2(filepath, target_name)
        print(f"файл скопирован как {target_name}")
    else:
        print(f"файл {filename} не найден на диске")

def show_help(): # справка команд CLI
    print("""
==================================================
              АДМИН-ПАНЕЛЬ MASHUPER
==================================================
  users             - список пользователей
  stats             - общая статистика
  blocked           - список заблокированных
  block <id>        - заблокировать пользователя
  unblock <id>      - разблокировать пользователя
  chat <id>         - показать диалог
  msg <id> <текст>  - отправить сообщение
  broadcast <текст> - рассылка всем
  file <id>         - скачать последний файл
  help              - справка
  exit / quit       - выход
==================================================
""")

async def main(): # интерактивная консоль админа
    init_db()
    print("админ-панель запущена. введите help для списка команд")
    while True:
        try:
            cmd = input("admin> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        parts = cmd.split()
        command = parts[0].lower()

        if command in ["exit", "quit"]:
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
                print(f"пользователь {parts[1]} заблокирован")
            else:
                print(f"пользователь {parts[1]} не найден")
        elif command == "unblock" and len(parts) > 1:
            if unblock_user(parts[1]):
                print(f"пользователь {parts[1]} разблокирован")
            else:
                print(f"пользователь {parts[1]} не найден")
        elif command == "chat" and len(parts) > 1:
            show_chat(int(parts[1]))
        elif command == "msg" and len(parts) > 2:
            await send_message(int(parts[1]), " ".join(parts[2:]))
        elif command == "broadcast" and len(parts) > 1:
            await broadcast(" ".join(parts[1:]))
        elif command == "file" and len(parts) > 1:
            download_user_file(int(parts[1]))
        else:
            print("неизвестная команда, введите help")

    global _admin_bot
    if _admin_bot:
        await _admin_bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())