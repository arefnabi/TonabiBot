"""Simple Telegram shop-support bot using only Python's standard library."""

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request


TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
DB_PATH = os.environ.get("BOT_DB_PATH", "support_bot.sqlite3")
API = f"https://api.telegram.org/bot{TOKEN}/"
MENU = "لطفاً نوع درخواست خود را انتخاب کنید:"
CATEGORIES = {
    "complaint": "ثبت شکایت",
    "criticism": "انتقاد",
    "suggestion": "پیشنهاد",
    "expert": "ارتباط با کارشناس",
}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, phone TEXT, step TEXT NOT NULL DEFAULT 'first_name', category TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS replies (admin_message_id INTEGER PRIMARY KEY, user_chat_id INTEGER NOT NULL)")


def api(method, data):
    request = urllib.request.Request(
        API + method,
        data=urllib.parse.urlencode(data).encode("utf-8"),
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))
    return result["result"]


def send(chat_id, text, keyboard=None, reply_to=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    if reply_to:
        data["reply_to_message_id"] = reply_to
    return api("sendMessage", data)


def category_keyboard():
    return {"keyboard": [[{"text": title}] for title in CATEGORIES.values()], "resize_keyboard": True}


def save_user(chat_id, **values):
    assignments = ", ".join(f"{key} = ?" for key in values)
    with db() as conn:
        conn.execute(f"UPDATE users SET {assignments} WHERE chat_id = ?", (*values.values(), chat_id))


def get_user(chat_id):
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()


def start(chat_id):
    with db() as conn:
        conn.execute("INSERT INTO users(chat_id, step) VALUES(?, 'first_name') ON CONFLICT(chat_id) DO UPDATE SET step='first_name', category=NULL", (chat_id,))
    send(chat_id, "سلام! به پشتیبانی فروشگاه خوش آمدید.\nلطفاً نام خود را وارد کنید:")


def process_message(message):
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    contact = message.get("contact")

    # A reply to a forwarded ticket from the configured admin is relayed to its owner.
    if str(chat_id) == ADMIN_CHAT_ID and message.get("reply_to_message"):
        replied_id = message["reply_to_message"]["message_id"]
        with db() as conn:
            row = conn.execute("SELECT user_chat_id FROM replies WHERE admin_message_id=?", (replied_id,)).fetchone()
        if row:
            try:
                api("copyMessage", {"chat_id": row["user_chat_id"], "from_chat_id": chat_id, "message_id": message["message_id"]})
                send(chat_id, "پاسخ شما برای کاربر ارسال شد.")
            except Exception as exc:
                print("Reply delivery failed:", exc)
                send(chat_id, "ارسال پاسخ انجام نشد؛ لطفاً دوباره تلاش کنید.")
            return

    if text == "/start":
        start(chat_id)
        return

    user = get_user(chat_id)
    if not user:
        start(chat_id)
        return

    step = user["step"]
    if step == "first_name":
        if not text or len(text) > 80:
            send(chat_id, "لطفاً نام معتبر وارد کنید:")
            return
        save_user(chat_id, first_name=text, step="last_name")
        send(chat_id, "ممنون. حالا نام خانوادگی خود را وارد کنید:")
    elif step == "last_name":
        if not text or len(text) > 100:
            send(chat_id, "لطفاً نام خانوادگی معتبر وارد کنید:")
            return
        save_user(chat_id, last_name=text, step="phone")
        send(chat_id, "شماره تلفن را بنویسید یا از دکمهٔ زیر برای فرستادن شمارهٔ تلگرام خود استفاده کنید:", {
            "keyboard": [[{"text": "ارسال شماره تلفن", "request_contact": True}]],
            "resize_keyboard": True, "one_time_keyboard": True,
        })
    elif step == "phone":
        phone = contact.get("phone_number", "") if contact and contact.get("user_id", chat_id) == chat_id else text
        normalized = re.sub(r"[\s()+.-]", "", phone)
        if not re.fullmatch(r"\+?\d{7,15}", normalized):
            send(chat_id, "شماره معتبر نیست. دوباره وارد کنید یا از دکمهٔ ارسال شماره تلفن استفاده کنید:")
            return
        save_user(chat_id, phone=phone, step="category")
        send(chat_id, MENU, category_keyboard())
    elif step in ("category", "conversation"):
        selected = next((key for key, title in CATEGORIES.items() if text == title), None)
        if step == "category" and selected:
            save_user(chat_id, category=selected, step="conversation")
            if selected == "expert":
                send(chat_id, "پیام خود را بنویسید؛ آن را برای کارشناس می‌فرستم. پاسخ کارشناس همین‌جا برایتان ارسال می‌شود.")
            else:
                send(chat_id, f"لطفاً جزئیات «{CATEGORIES[selected]}» را در یک پیام بنویسید:")
            return
        if not text and not message.get("photo") and not message.get("document") and not message.get("voice"):
            send(chat_id, "لطفاً پیام متنی یا فایل خود را بفرستید.")
            return
        category = user["category"] or "expert"
        label = CATEGORIES.get(category, "ارتباط با کارشناس")
        summary = (f"درخواست جدید: {label}\n"
                   f"نام: {user['first_name']} {user['last_name']}\n"
                   f"تلفن: {user['phone']}\n"
                   f"شناسه کاربر: {chat_id}\n\n"
                   "برای پاسخ به کاربر، روی این پیام در چت مدیر Reply کنید.")
        try:
            forwarded = send(int(ADMIN_CHAT_ID), summary)
            copied = api("copyMessage", {"chat_id": int(ADMIN_CHAT_ID), "from_chat_id": chat_id, "message_id": message["message_id"]})
            with db() as conn:
                conn.execute("INSERT OR REPLACE INTO replies(admin_message_id, user_chat_id) VALUES(?, ?)", (forwarded["message_id"], chat_id))
                conn.execute("INSERT OR REPLACE INTO replies(admin_message_id, user_chat_id) VALUES(?, ?)", (copied["message_id"], chat_id))
            send(chat_id, "پیام شما ثبت شد و برای پشتیبانی ارسال شد. اگر نیاز به ادامهٔ گفتگو دارید، پیام بعدی را همین‌جا بفرستید.", category_keyboard())
        except Exception as exc:
            print("Ticket delivery failed:", exc)
            send(chat_id, "ارسال پیام انجام نشد. کمی بعد دوباره تلاش کنید یا /start را بزنید.")


def main():
    if not TOKEN or not ADMIN_CHAT_ID:
        raise SystemExit("لطفاً TELEGRAM_BOT_TOKEN و ADMIN_CHAT_ID را در متغیرهای محیطی تنظیم کنید.")
    init_db()
    try:
        offset = int(api("getUpdates", {"timeout": 0, "allowed_updates": json.dumps(["message"])}))
    except Exception:
        offset = 0
    print("Support bot is running.")
    while True:
        try:
            updates = api("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": json.dumps(["message"])})
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    process_message(update["message"])
        except (urllib.error.URLError, TimeoutError) as exc:
            print("Connection error:", exc)
            time.sleep(3)
        except Exception as exc:
            print("Update error:", exc)
            time.sleep(2)


if __name__ == "__main__":
    main()
