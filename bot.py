import os
import json
import logging
from html import escape
from datetime import datetime
import random
import threading
import time

import requests
from flask import Flask, request

# ======= Конфігурація =======
TOKEN = os.getenv("API_TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable API_TOKEN is required")

try:
    ADMIN_ID = int(os. getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

app = Flask(__name__)
logging.basicConfig(level=logging. INFO)
logger = logging.getLogger(__name__)

# ======= Стан чатів =======
active_chats = {}  # chat_id -> status
admin_targets = {}  # admin_id -> target_chat_id

# ======= Idle mode (холостой ход) =======
idle_mode_enabled = True
idle_min_interval = 60
idle_max_interval = 600
idle_thread = None
idle_stop_event = threading.Event()

# ======= Константи з красивим форматуванням =======
WELCOME_TEXT = (
    "🤖 <b>Привіт!  Ласкаво просимо в бухгалтерський бот</b>\n\n"
    "Я вам допоможу з питаннями щодо:\n"
    "📋 Розробки ботів\n"
    "💼 Консультаціями\n"
    "📞 Технічної підтримки\n\n"
    "Оберіть дію з меню нижче 👇"
)

SCHEDULE_TEXT = (
    "📅 <b>Графік роботи</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🏢 <b>Робочі дні:</b>\n"
    "  <b>Пн–Чт:</b> 09:00 – 18:00 ⏰\n"
    "  <b>Пт:</b> 09:00 – 15:00 ⏰\n\n"
    "🌙 <b>Вихідні:</b>\n"
    "  <b>Сб–Нд:</b> 🚫\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Коментар: </i> Якщо ви напишете в позаробочий час,\n"
    "ваш запит буде обов'язково розглянутий!  😊"
)

FAQ_TEXT = (
    "❓ <b>Часті питання</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>⏱️ Скільки часу займає розробка бота?</b>\n"
    "└─ від <u>1 до 7 робочих днів</u>\n"
    "    залежно від складності\n\n"
    "<b>💰 Коли потрібно оплатити? </b>\n"
    "└─ <u>Після виконання замовлення</u>\n"
    "    спочатку розробка, потім оплата ✅\n\n"
    "<b>🔄 Чи можна змінити завдання?</b>\n"
    "└─ Так!  Невеликі зміни обговорюються\n"
    "    з адміністратором\n\n"
    "<b>📞 Як зв'язатись з адміністратором?</b>\n"
    "└─ Натисніть <b>'Поставити питання'</b>\n"
    "    і опишіть вашу проблему\n\n"
    "<b>🕐 Графік роботи? </b>\n"
    "└─ Натисніть <b>'Графік роботи'</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Не знайшли відповідь? </i>\n"
    "Звертайтесь до адміністратора! 😊"
)

OFF_HOURS_TEXT = (
    "⏰ <b>Адміністрація в даний момент не працює</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "❌ <b>Час зараз:</b> позаробочий\n\n"
    "✅ <b>Але не хвилюйтесь: </b>\n"
    "   Ваш запит буде збережено\n"
    "   Адміністратор обов'язково вам\n"
    "   відповідить першим ділом!  🚀\n\n"
    "💡 <b>Порада:</b> переглядайте FAQ або графік роботи\n"
    "   можливо там знайдете відповідь"
)

PAYMENT_TEXT = (
    "💳 <b>Реквізити для оплати</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🏦 <b>Отримувач:</b>\n"
    "  ФОП Романюк Анжела Василівна\n\n"
    "💰 <b>IBAN:</b>\n"
    "  <code>UA033220010000026006340057875</code>\n\n"
    "🆔 <b>ЄДРПОУ:</b>\n"
    "  <code>3316913762</code>\n\n"
    "📝 <b>Призначення платежу:</b>\n"
    "  <i>Оплата за консультаційні послуги</i>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "✅ Після оплати напишіть боту,\n"
    "щоб ми все зареєстрували!"
)

CHAT_START_TEXT = (
    "👋 <b>Чат роз��очинається</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Ви підключені до адміністратора.\n"
    "Напишіть своє питання або проблему.\n\n"
    "<i>Нижче є кнопка 'Завершити чат'</i>\n"
    "<i>Натисніть її, коли завершите спілкування</i>"
)

CHAT_CLOSED_TEXT = (
    "⛔️ <b>Чат завершено</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Дякуємо за спілкування!  😊\n"
    "Ви повернулись у головне меню.\n\n"
    "Якщо потрібна ще допомога —\n"
    "просто натисніть меню знизу! 👇"
)

ADMIN_CHAT_CLOSED_TEXT = (
    "✅ <b>Чат успішно закрито</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Користувач:  <b>%s</b>\n"
    "Дякуємо за вашу роботу! 💼"
)

# ======= Функція для перевірки робочого часу =======
def is_working_hours():
    """
    Перевіряє, чи зараз робочий час. 
    """
    now = datetime.utcnow()
    now_local = now.replace(hour=now.hour + 2)
    
    weekday = now_local.weekday()
    hour = now_local.hour
    minute = now_local.minute
    current_time = hour * 60 + minute
    
    if weekday in (5, 6):
        return False
    
    if weekday in (0, 1, 2, 3):
        start = 9 * 60
        end = 18 * 60
        return start <= current_time < end
    
    if weekday == 4:
        start = 9 * 60
        end = 15 * 60
        return start <= current_time < end
    
    return False

# ======= Функції для холостого ходу =======
def simulate_user_activity():
    """
    Імітує користувача що натискає на інлайн кнопку.
    """
    activity_log = [
        "☑️ Користувач натиснув кнопку 'Графік роботи'",
        "☑️ Користувач натиснув кнопку 'Часті питання'",
        "☑️ Користувач натиснув кнопку 'Поставити питання'",
        "☑️ Користувач переглядає меню",
        "☑️ Користувач натиснув кнопку 'Реквізити для оплати'",
        "☑️ Користувач натиснув 'Меню'",
    ]
    
    activity = random.choice(activity_log)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[IDLE MODE] {timestamp} → {activity}")

def idle_mode_worker():
    """
    Фоновий потік для імітації активності користувача.
    """
    logger.info("[IDLE MODE] Холостий хід активований.  Буде імітуватися активність кожні 1-10 хвилин.")
    
    while not idle_stop_event.is_set():
        try:
            wait_time = random.randint(idle_min_interval, idle_max_interval)
            logger.info(f"[IDLE MODE] Наступна імітація активності через {wait_time} секунд ({wait_time / 60:. 1f} хвилин)...")
            
            if idle_stop_event.wait(timeout=wait_time):
                break
            
            simulate_user_activity()
            
        except Exception as e:
            logger.error(f"[IDLE MODE] Помилка у потоці холостого ходу: {e}")
            time.sleep(5)

def start_idle_mode():
    """Запускає фоновий потік холостого ходу."""
    global idle_thread
    
    if idle_mode_enabled and idle_thread is None:
        idle_stop_event.clear()
        idle_thread = threading.Thread(target=idle_mode_worker, daemon=True)
        idle_thread.start()
        logger.info("[IDLE MODE] Потік запущен")

def stop_idle_mode():
    """Зупиняє фоновий потік холостого ходу."""
    global idle_thread
    
    if idle_thread is not None: 
        idle_stop_event. set()
        idle_thread. join(timeout=2)
        idle_thread = None
        logger. info("[IDLE MODE] Потік зупинен")

# ======= Розмітки з красивим дизайном =======
def main_menu_markup():
    return {
        "keyboard": [
            [{"text": "📋 Меню"}, {"text": "📖 FAQ"}],
            [{"text": "💬 Поставити питання"}, {"text": "🕐 Графік"}],
            [{"text": "💳 Реквізити"}, {"text":  "❓ Допомога"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Виберіть дію з меню.. .",
    }

def user_finish_markup():
    return {
        "keyboard": [[{"text": "✅ Завершити чат"}, {"text": "🏠 Меню"}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

def admin_reply_markup(user_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✉️ Відповісти", "callback_data": f"reply_{user_id}"},
                {"text": "❌ Закрити", "callback_data":  f"close_{user_id}"},
            ],
        ]
    }

# ======= Хелпери для відправки повідомлень =======
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception: 
        app.logger.exception("Failed to send message")
        return None

def send_media(chat_id, msg):
    """Forward a single-file media by file_id to chat_id."""
    for key, api in [
        ("photo", "sendPhoto"),
        ("document", "sendDocument"),
        ("video", "sendVideo"),
        ("audio", "sendAudio"),
        ("voice", "sendVoice"),
    ]:
        if key in msg:
            file_id = msg[key][-1]["file_id"] if key == "photo" else msg[key]["file_id"]
            url = f"https://api.telegram.org/bot{TOKEN}/{api}"
            payload = {"chat_id": chat_id, key: file_id}
            if "caption" in msg:
                payload["caption"] = msg. get("caption")
            try:
                resp = requests.post(url, json=payload, timeout=8)
                resp.raise_for_status()
                return True
            except Exception:
                app.logger.exception("Failed to send media")
                return False
    return False

# ======= Webhook handler =======
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)

    # callback_query handling (inline buttons)
    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        from_id = cb["from"]["id"]
        message = cb. get("message") or {}
        chat_id = message.get("chat", {}).get("id")

        # Admin actions:  reply to a user
        if data. startswith("reply_") and from_id == ADMIN_ID:
            try:
                user_id = int(data.split("_", 1)[1])
            except Exception:
                return "ok", 200
            active_chats[user_id] = "active"
            admin_targets[from_id] = user_id
            send_message(from_id, f"🎯 <b>Ви тепер спілкуєтесь з користувачем: </b> <code>{user_id}</code>\n\nТип <b>'завершити'</b> щоб закрити чат.", parse_mode="HTML")
            send_message(user_id, CHAT_START_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
            return "ok", 200

        # Admin closes chat
        if data. startswith("close_") and from_id == ADMIN_ID: 
            try:
                user_id = int(data.split("_", 1)[1])
            except Exception:
                return "ok", 200
            active_chats.pop(user_id, None)
            if admin_targets.get(from_id) == user_id:
                admin_targets. pop(from_id, None)
            send_message(user_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
            send_message(from_id, ADMIN_CHAT_CLOSED_TEXT % user_id, parse_mode="HTML")
            return "ok", 200

        return "ok", 200

    # message handling
    msg = update.get("message")
    if not msg:
        return "ok", 200

    cid = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    text = msg.get("text", "") or ""

    # /start and menu
    if text.startswith("/start") or text == "🏠 Меню":
        active_chats. pop(user_id, None)
        admin_targets.pop(ADMIN_ID, None)
        send_message(cid, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # Show menu
    if text == "📋 Меню":
        send_message(cid, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # Show schedule
    if text == "🕐 Графік":
        send_message(cid, SCHEDULE_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # Show FAQ
    if text == "📖 FAQ":
        send_message(cid, FAQ_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # Show payments
    if text == "💳 Реквізити":
        send_message(cid, PAYMENT_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # Show help (same as menu)
    if text == "❓ Допомога": 
        send_message(cid, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        return "ok", 200

    # User requests admin
    if text == "💬 Поставити питання":
        if cid not in active_chats:
            active_chats[cid] = "pending"
            
            if not is_working_hours():
                send_message(cid, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
            else:
                send_message(cid, "⏳ <b>Адміністратор прочитає ваш запит в найближчий час!</b>\n\nОчікуйте.. .", reply_markup=user_finish_markup(), parse_mode="HTML")
            
            notif = (
                f"🔔 <b>НОВИЙ ЗАПИТ ВІД КОРИСТУВАЧА</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User ID: </b> <code>{cid}</code>\n\n"
                f"⏰ <b>Час:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"Натисніть кнопку <b>'✉️ Відповісти'</b> щоб почати чат"
            )
            send_message(ADMIN_ID, notif, parse_mode="HTML", reply_markup=admin_reply_markup(cid))
            if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                send_media(ADMIN_ID, msg)
        else:
            if not is_working_hours():
                send_message(cid, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
            else:
                send_message(cid, "⏳ Ваш запит уже отправлен. Очікуйте відповіді.. .", reply_markup=user_finish_markup(), parse_mode="HTML")
        return "ok", 200

    # User closes chat
    if text == "✅ Завершити чат" and cid in active_chats:
        active_chats. pop(cid, None)
        if admin_targets.get(ADMIN_ID) == cid:
            admin_targets.pop(ADMIN_ID, None)
        send_message(cid, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        send_message(ADMIN_ID, f"✅ Користувач <code>{cid}</code> завершив чат.", parse_mode="HTML")
        return "ok", 200

    # If user is in active chat, forward messages to admin
    if cid in active_chats and active_chats[cid] == "active" and user_id != ADMIN_ID:
        if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
            send_media(ADMIN_ID, msg)
            send_message(ADMIN_ID, f"📎 <b>Медіа від</b> <code>{cid}</code>", parse_mode="HTML", reply_markup=admin_reply_markup(cid))
        elif text: 
            send_message(ADMIN_ID, f"💬 <b>Користувач {cid}:</b>\n<pre>{escape(text)}</pre>", parse_mode="HTML", reply_markup=admin_reply_markup(cid))
        return "ok", 200

    # Admin sending a message to the selected target
    if cid == ADMIN_ID: 
        target = admin_targets.get(ADMIN_ID)
        if not target:
            send_message(ADMIN_ID, "⚠️ <b>Спочатку виберіть користувача!</b>\n\nНатисніть на кнопку <b>'✉️ Відповісти'</b> у його повідомленні.", reply_markup=main_menu_markup(), parse_mode="HTML")
            return "ok", 200

        if text and text.lower().startswith("завершити"):
            active_chats.pop(target, None)
            admin_targets.pop(ADMIN_ID, None)
            send_message(target, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
            send_message(ADMIN_ID, f"✅ Чат з користувачем <code>{target}</code> закрито.", parse_mode="HTML")
            return "ok", 200

        if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
            send_media(target, msg)
            send_message(target, "📎 <b>Адміністратор надіслав медіа</b>", reply_markup=user_finish_markup(), parse_mode="HTML")
        elif text:
            send_message(target, f"✉️ <b>Адміністратор:</b>\n{text}", reply_markup=user_finish_markup())
        return "ok", 200

    # Fallback:  ask user to use menu
    send_message(cid, "🤔 <b>Не розумію команду</b>\n\nБудь ласка, скористайтеся меню нижче 👇", reply_markup=main_menu_markup(), parse_mode="HTML")
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

if __name__ == "__main__": 
    # Запускаємо холостий хід
    start_idle_mode()
    
    port = int(os.getenv("PORT", "5000"))
    try:
        app.run("0.0.0.0", port=port)
    finally:
        # Зупиняємо холостий хід при завершенні приложения
        stop_idle_mode()
