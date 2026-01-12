import os
import logging
from html import escape
from datetime import datetime, timedelta
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
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:5000")
WEBHOOK_URL = f"{SERVER_URL}/webhook"

app = Flask(__name__)
logging.basicConfig(level=logging. INFO)
logger = logging.getLogger(__name__)

# ======= Стан чатів =======
active_chats = {}
admin_targets = {}

# ======= Keep-Alive Mode (Симуляція активності сервера) =======
keep_alive_enabled = True
keep_alive_interval = 300  # 5 хвилин (можна налаштувати)
keep_alive_thread = None
keep_alive_stop_event = threading.Event()

# ======= ОНОВЛЕНІ КОНСТАНТИ З ПРОСТИМ ДИЗАЙНОМ =======
WELCOME_TEXT = (
    "<b>Ласкаво просимо!    👋</b>\n\n"
    "Оберіть, як ми можемо вам допомогти:"
)

SCHEDULE_TEXT = (
    "<b>Графік роботи</b>\n\n"
    "<b>Пн–Чт: </b> 09:00 – 18:00\n"
    "<b>Пт: </b> 09:00 – 15:00\n"
    "<b>Сб–Нд: </b> Вихідні\n\n"
    "<i>Запити в позаробочий час будуть розглянуті, але згодом ✓</i>"
)

FAQ_TEXT = (
    "<b>Часті питання</b>\n\n"
    "Натисніть кнопку під питанням, щоб дізнатися відповідь:"
)

OFF_HOURS_TEXT = (
    "<b>Позаробочий час ⏰</b>\n\n"
    "Адміністрація зараз не працює, але ваш запит буде розглянутий першим ділом.\n\n"
    "Спробуйте переглянути FAQ або графік роботи."
)

PAYMENT_TEXT = (
    "<b>Реквізити для оплати</b>\n\n"
    "Якщо ви купите наш бот, тут будуть ваші реквізити 😊"
)

CHAT_START_TEXT = (
    "<b>Чат розпочинається 💬</b>\n\n"
    "Ви підключені до адміністратора.\n"
    "Напишіть своє питання."
)

CHAT_CLOSED_TEXT = (
    "<b>Чат закритий ✓</b>\n\n"
    "Дякуємо за спілкування!"
)

ADMIN_CHAT_CLOSED_TEXT = (
    "Чат закритий ✓\n"
    "Користувач:    <code>%s</code>"
)

ADMIN_MENU_TEXT = (
    "<b>Меню адміністратора</b>\n\n"
    "/help – довідка"
)

# ======= Функція для перевірки робочого часу =======
def is_working_hours():
    try:
        now = datetime.utcnow()
        now_local = now + timedelta(hours=2)
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
    except Exception as e: 
        logger.error(f"Error checking working hours: {e}")
        return True

# ======= KEEP-ALIVE:  Симуляція активності сервера =======
class KeepAliveManager: 
    """Менеджер для утримання сервера в активному стані"""
    
    def __init__(self, interval=300):
        self.interval = interval  # інтервал у секундах
        self.thread = None
        self.stop_event = threading.Event()
        self.request_count = 0
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def log_server_health(self):
        """Логування здоров'я сервера"""
        uptime = datetime.now() - self.start_time
        with self.lock:
            count = self.request_count
        
        logger.info(
            f"[KEEP-ALIVE] 💚 Сервер активний | "
            f"Запитів оброблено: {count} | "
            f"Час роботи: {uptime}"
        )
    
    def perform_health_check(self):
        """Перевірка здоров'я сервера через HTTP запит до себе"""
        try:
            # Запит до власного сервера (внутрішній health check)
            resp = requests.get(f"{SERVER_URL}/", timeout=5)
            if resp.status_code == 200:
                logger.debug("[KEEP-ALIVE] ✅ Self-health check пройден")
                return True
            else:
                logger.warning(f"[KEEP-ALIVE] ⚠️ Health check статус: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[KEEP-ALIVE] ❌ Health check помилка: {e}")
            return False
    
    def perform_telegram_check(self):
        """Перевірка з'єднання з Telegram API"""
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getMe"
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            result = resp.json()
            if result. get("ok"):
                logger. debug(f"[KEEP-ALIVE] ✅ Telegram API відповідає:  {result['result']['first_name']}")
                return True
            else:
                logger. warning("[KEEP-ALIVE] ⚠️ Telegram API не відповідає нормально")
                return False
        except Exception as e:
            logger.error(f"[KEEP-ALIVE] ❌ Telegram перевірка помилка: {e}")
            return False
    
    def keep_alive_worker(self):
        """Worker для постійного утримання сервера в активному стані"""
        logger.info("[KEEP-ALIVE] 🔄 Keep-alive механізм запущен")
        
        while not self.stop_event.is_set():
            try:
                # Чекаємо інтервал (з можливістю перривання)
                if self.stop_event.wait(timeout=self.interval):
                    break
                
                # Виконуємо health check
                self.perform_health_check()
                self.perform_telegram_check()
                
                # Логуємо стан сервера
                self.log_server_health()
                
            except Exception as e:
                logger.error(f"[KEEP-ALIVE] ❌ Помилка у worker: {e}")
                time. sleep(5)
        
        logger.info("[KEEP-ALIVE] 🛑 Keep-alive механізм зупинен")
    
    def increment_request_counter(self):
        """Збільшити лічильник оброблених запитів"""
        with self.lock:
            self.request_count += 1
    
    def start(self):
        """Запустити keep-alive менеджер"""
        try:
            if self.thread is None or not self.thread.is_alive():
                self.stop_event.clear()
                self.thread = threading.Thread(
                    target=self.keep_alive_worker,
                    daemon=True,
                    name="KeepAliveManager"
                )
                self. thread.start()
                logger. info(f"[KEEP-ALIVE] ✅ Keep-alive запущен (інтервал: {self.interval}s)")
                return True
            else:
                logger.warning("[KEEP-ALIVE] ⚠️ Keep-alive вже запущен")
                return False
        except Exception as e:
            logger. error(f"[KEEP-ALIVE] ❌ Помилка при запуску:  {e}")
            return False
    
    def stop(self):
        """Зупинити keep-alive менеджер"""
        try:
            if self.thread is not None and self.thread.is_alive():
                self.stop_event.set()
                self.thread.join(timeout=3)
                logger.info("[KEEP-ALIVE] ✅ Keep-alive зупинен")
                return True
            else:
                logger.warning("[KEEP-ALIVE] ⚠️ Keep-alive не був запущен")
                return False
        except Exception as e:
            logger. error(f"[KEEP-ALIVE] ❌ Помилка при зупинці: {e}")
            return False
    
    def get_status(self):
        """Отримати поточний статус"""
        uptime = datetime.now() - self.start_time
        with self.lock:
            count = self.request_count
        
        return {
            "is_running": self.thread is not None and self.thread.is_alive(),
            "interval": self.interval,
            "requests_processed": count,
            "uptime":  str(uptime),
            "last_check": datetime.now().isoformat()
        }

# Глобальний об'єкт keep-alive менеджера
keep_alive_manager = KeepAliveManager(interval=keep_alive_interval)

# ======= ОНОВЛЕНІ РОЗМІТКИ З ПРОСТИМ ДИЗАЙНОМ =======
def main_menu_markup():
    return {
        "keyboard": [
            [{"text": "❓ FAQ"}],
            [{"text": "📞 Поставити питання"}],
            [{"text":  "📅 Графік"}, {"text": "💳 Реквізити"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "input_field_placeholder": "Виберіть опцію..   .",
    }

def user_finish_markup():
    return {
        "keyboard": [[{"text": "✓ Завершити"}, {"text": "🏠 Меню"}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

def admin_reply_markup(user_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✉️ Відповісти", "callback_data": f"reply_{user_id}"},
            ],
            [
                {"text": "✗ Закрити", "callback_data":  f"close_{user_id}"},
            ],
        ]
    }

# ======= ІНТЕРАКТИВНЕ FAQ З КНОПКАМИ =======
def faq_markup():
    """Кнопки для FAQ"""
    return {
        "inline_keyboard": [
            [{"text": "⏱️ Скільки часу займає розробка?", "callback_data": "faq_time"}],
            [{"text": "💰 Коли оплатити?", "callback_data":  "faq_payment"}],
            [{"text": "🔄 Можна змінити завдання?", "callback_data": "faq_change"}],
            [{"text": "🏠 Назад", "callback_data": "back_to_menu"}],
        ]
    }

faq_answers = {
    "faq_time": (
        "<b>⏱️ Скільки часу займає розробка бота?</b>\n\n"
        "Зазвичай від 1 до 7 робочих днів, залежно від складності проекту."
    ),
    "faq_payment": (
        "<b>💰 Коли потрібно оплатити?  </b>\n\n"
        "Оплата здійснюється <b>після завершення</b> роботи.    "
        "Спочатку ми розробляємо, потім ви оплачуєте."
    ),
    "faq_change": (
        "<b>🔄 Чи можна змінити завдання?</b>\n\n"
        "Так!    Невеликі зміни обговорюються з адміністратором "
        "і можуть бути внесені в процес розробки."
    ),
}

# ======= Хелпери для відправки повідомлень =======
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = __import__('json').dumps(reply_markup)
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    try:
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        keep_alive_manager.increment_request_counter()  # Лічильник активності
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return None

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    """Редактирует сообщение (для кнопок FAQ)"""
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id, 
        "message_id":  message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup is not None:
        payload["reply_markup"] = __import__('json').dumps(reply_markup)
    try:
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        keep_alive_manager. increment_request_counter()  # Лічильник активності
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to edit message:  {e}")
        return None

def send_media(chat_id, msg):
    try:
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
                    keep_alive_manager.increment_request_counter()  # Лічильник активності
                    return True
                except Exception as e: 
                    logger.error(f"Failed to send media to {chat_id}: {e}")
                    return False
    except Exception as e:
        logger.error(f"Error in send_media: {e}")
    return False

# ======= Обработка команд в отдельном потоке =======
def handle_command(command, chat_id, msg, user_id):
    try:
        logger.info(f"[THREAD] Команда:  {command} від {chat_id}")
        
        # ADMIN COMMANDS
        if chat_id == ADMIN_ID and command == "/help":
            send_message(chat_id, ADMIN_MENU_TEXT, parse_mode="HTML")
        elif command. startswith("/start") or command == "🏠 Меню":
            active_chats. pop(user_id, None)
            admin_targets.pop(ADMIN_ID, None)
            send_message(chat_id, WELCOME_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "📅 Графік":
            send_message(chat_id, SCHEDULE_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "❓ FAQ":
            send_message(chat_id, FAQ_TEXT, reply_markup=faq_markup(), parse_mode="HTML")
        elif command == "💳 Реквізити":
            send_message(chat_id, PAYMENT_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
        elif command == "📞 Поставити питання":
            if chat_id not in active_chats:
                active_chats[chat_id] = "pending"
                if not is_working_hours():
                    send_message(chat_id, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                else: 
                    send_message(chat_id, "Адміністратор прочитає ваш запит в найближчий час..   .", reply_markup=user_finish_markup(), parse_mode="HTML")
                
                notif = (
                    f"<b>НОВИЙ ЗАПИТ</b>\n\n"
                    f"User ID: <code>{chat_id}</code>\n"
                    f"Час: {datetime.now().strftime('%H:%M:%S')}"
                )
                send_message(ADMIN_ID, notif, parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                    send_media(ADMIN_ID, msg)
            else:
                if not is_working_hours():
                    send_message(chat_id, OFF_HOURS_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                else:
                    send_message(chat_id, "Ваш запит уже отправлен.    Очікуйте..   .", reply_markup=user_finish_markup(), parse_mode="HTML")
        elif command == "✓ Завершити" and chat_id in active_chats:
            active_chats. pop(chat_id, None)
            if admin_targets.get(ADMIN_ID) == chat_id:
                admin_targets.pop(ADMIN_ID, None)
            send_message(chat_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
            send_message(ADMIN_ID, f"Користувач завершив чат", parse_mode="HTML")
        else:
            send_message(chat_id, "Команда не розпізнана.  Виберіть опцію з меню.", reply_markup=main_menu_markup(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"[THREAD ERROR] {e}", exc_info=True)

# ======= Webhook handler =======
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    logger.info(f"[WEBHOOK] {request.method}")
    keep_alive_manager.increment_request_counter()  # Лічильник активності
    
    if request.method == "GET":
        return "OK", 200

    if request.method == "POST":
        try:
            update = request.get_json(force=True)
            logger.info(f"[WEBHOOK] Update отримано")
            
            # callback_query handling
            if "callback_query" in update: 
                cb = update["callback_query"]
                data = cb.get("data", "")
                from_id = cb["from"]["id"]
                message = cb. get("message") or {}
                chat_id = message.get("chat", {}).get("id")
                message_id = message.get("message_id")

                # FAQ callbacks
                if data in faq_answers:
                    edit_message(chat_id, message_id, faq_answers[data], reply_markup=faq_markup())
                    return "ok", 200

                # Back to menu
                if data == "back_to_menu":
                    edit_message(chat_id, message_id, WELCOME_TEXT, reply_markup=main_menu_markup())
                    return "ok", 200

                # Admin reply
                if data. startswith("reply_") and from_id == ADMIN_ID: 
                    try:
                        user_id = int(data.split("_", 1)[1])
                    except Exception as e:
                        logger.error(f"Error parsing user_id:  {e}")
                        return "ok", 200
                    active_chats[user_id] = "active"
                    admin_targets[from_id] = user_id
                    send_message(from_id, f"Спілкуєтесь з користувачем {user_id}\nТип 'завершити' для закриття", parse_mode="HTML")
                    send_message(user_id, CHAT_START_TEXT, reply_markup=user_finish_markup(), parse_mode="HTML")
                    return "ok", 200

                # Admin close chat
                if data. startswith("close_") and from_id == ADMIN_ID:
                    try: 
                        user_id = int(data.split("_", 1)[1])
                    except Exception as e:
                        logger. error(f"Error parsing user_id: {e}")
                        return "ok", 200
                    active_chats.pop(user_id, None)
                    if admin_targets.get(from_id) == user_id:
                        admin_targets.pop(from_id, None)
                    send_message(user_id, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                    send_message(from_id, ADMIN_CHAT_CLOSED_TEXT % user_id, parse_mode="HTML")
                    return "ok", 200

                return "ok", 200

            # message handling
            msg = update.get("message")
            if not msg:
                logger.warning("[WEBHOOK] Немає message")
                return "ok", 200

            chat_id = msg. get("chat", {}).get("id")
            user_id = msg.get("from", {}).get("id")
            text = msg.get("text", "") or ""

            logger.info(f"[WEBHOOK] chat_id={chat_id}, text='{text}'")

            # Ищем команду
            command = None
            for possible in ("/start", "/help", "🏠 Меню", "📅 Графік", "❓ FAQ", "💳 Реквізити", "📞 Поставити питання", "✓ Завершити"):
                if text.startswith(possible) or text == possible:
                    command = text. strip()
                    logger.info(f"[WEBHOOK] Команда: {command}")
                    break

            if command:
                threading.Thread(target=handle_command, args=(command, chat_id, msg, user_id), daemon=True).start()
                return "ok", 200

            # Special case: чат администратор-пользователь
            if chat_id in active_chats and active_chats[chat_id] == "active" and user_id != ADMIN_ID:
                if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                    send_media(ADMIN_ID, msg)
                    send_message(ADMIN_ID, f"Медіа від {chat_id}", parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                elif text: 
                    send_message(ADMIN_ID, f"<b>{chat_id}:</b>\n{text}", parse_mode="HTML", reply_markup=admin_reply_markup(chat_id))
                return "ok", 200

            if chat_id == ADMIN_ID:
                target = admin_targets.get(ADMIN_ID)
                if target:
                    if text and text.lower().startswith("завершити"):
                        active_chats.pop(target, None)
                        admin_targets.pop(ADMIN_ID, None)
                        send_message(target, CHAT_CLOSED_TEXT, reply_markup=main_menu_markup(), parse_mode="HTML")
                        send_message(ADMIN_ID, f"Чат закритий", parse_mode="HTML")
                        return "ok", 200
                    if any(k in msg for k in ("photo", "document", "video", "audio", "voice")):
                        send_media(target, msg)
                        send_message(target, "Адміністратор надіслав медіа", reply_markup=user_finish_markup(), parse_mode="HTML")
                    elif text:
                        send_message(target, text, reply_markup=user_finish_markup(), parse_mode="HTML")
                    return "ok", 200

            return "ok", 200

        except Exception as e:
            logger. error(f"[WEBHOOK ERROR] {e}", exc_info=True)
            return "error", 500

@app.route("/", methods=["GET"])
def index():
    return "✅ Бот запущен", 200

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint для перевірки здоров'я сервера"""
    status = keep_alive_manager.get_status()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "keep_alive":  status
    }, 200

if __name__ == "__main__": 
    keep_alive_manager.start()  # Запускаємо keep-alive менеджер
    register_webhook()
    port = int(os.getenv("PORT", "5000"))
    try:
        app.run("0.0.0.0", port=port, threaded=True)
    except Exception as e:
        logger.error(f"Error running app: {e}")
    finally:
        keep_alive_manager.stop()  # Зупиняємо keep-alive менеджер
        delete_webhook()
