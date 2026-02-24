# Telegram Bot - Simple Event Reporting
import os
import time
import json
import requests
import threading
import traceback
import datetime
from html import escape
from flask import Flask, request
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# ====== Логирование ======
def MainProtokol(s, ts='Запис'):
    dt = time.strftime('%d.%m.%Y %H:%M:') + '00'
    try:
        with open('log.txt', 'a', encoding='utf-8') as f:
            f.write(f"{dt};{ts};{s}\n")
    except Exception as e:
        print("Ошибка записи в лог:", e)

# ====== Обработчик ошибок ======
def cool_error_handler(exc, context="", send_to_telegram=False):
    exc_type = type(exc).__name__
    tb_str = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    readable_msg = (
        "\n" + "=" * 40 + "\n"
        f"[ERROR] {exc_type}\n"
        f"Context: {context}\n"
        f"Time: {ts}\n"
        "Traceback:\n"
        f"{tb_str}"
        + "=" * 40 + "\n"
    )
    try:
        with open('critical_errors.log', 'a', encoding='utf-8') as f:
            f.write(readable_msg)
    except Exception as write_err:
        print("Не удалось записать в 'critical_errors.log':", write_err)
    print(readable_msg)

# ====== Фоновый отладчик времени ======
def time_debugger():
    while True:
        print("[DEBUG]", time.strftime('%Y-%m-%d %H:%M:%S'))
        time.sleep(300)

# ====== Конфигурация (читаем из Render переменных окружения) ======
TOKEN = os.getenv("API_TOKEN", "").strip()
ADMIN_ID_STR = os.getenv("ADMIN_ID", "0").strip()

try:
    ADMIN_ID = int(ADMIN_ID_STR)
except Exception:
    ADMIN_ID = 0
    print(f"[WARN] ADMIN_ID не является числом: {ADMIN_ID_STR}")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").strip()
PORT = int(os.getenv("PORT", "5000"))

if not TOKEN:
    print("[ERROR] API_TOKEN не установлен!")
    raise ValueError("API_TOKEN не установлен в переменных окружения Render")

if ADMIN_ID == 0:
    print("[WARN] ADMIN_ID не установлен или равен 0")

print(f"[INFO] Бот запущен с параметрами:")
print(f"  - TOKEN: {'***' + TOKEN[-5:] if len(TOKEN) > 5 else '***'}")
print(f"  - ADMIN_ID: {ADMIN_ID}")
print(f"  - WEBHOOK_HOST: {WEBHOOK_HOST}")
print(f"  - PORT: {PORT}")

if TOKEN and WEBHOOK_HOST:
    webhook_domain = WEBHOOK_HOST.replace("https://", "").replace("http://", "").rstrip("/")
    WEBHOOK_URL = f"https://{webhook_domain}/webhook"
else:
    WEBHOOK_URL = ""

print(f"[INFO] WEBHOOK_URL: {WEBHOOK_URL}")

# ====== Установка webhook ======
def set_webhook():
    if not TOKEN:
        print("[WARN] TOKEN is not set, webhook not initialized.")
        return
    if not WEBHOOK_URL:
        print("[INFO] WEBHOOK_HOST not set; skip setting webhook.")
        return
    try:
        r_delete = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
            timeout=5
        )
        print(f"[INFO] Delete webhook response: {r_delete.status_code}")
        
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={"url": WEBHOOK_URL},
            timeout=5
        )
        
        if r.ok:
            result = r.json()
            print(f"[SUCCESS] Webhook успешно установлен!")
            print(f"[INFO] Response: {result}")
            MainProtokol(f"Webhook установлен: {WEBHOOK_URL}")
        else:
            print(f"[ERROR] Ошибка при установке webhook: {r.status_code}")
            print(f"[ERROR] Response: {r.text}")
            MainProtokol(f"setWebhook failed: {r.status_code} {r.text}", ts='WARN')
    except Exception as e:
        cool_error_handler(e, context="set_webhook")

set_webhook()

# ====== UI helpers ======
def send_chat_action(chat_id, action='typing'):
    if not TOKEN:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{TOKEN}/sendChatAction',
            data={'chat_id': chat_id, 'action': action},
            timeout=3
        )
    except Exception:
        pass

def get_reply_buttons():
    return {
        "keyboard": [
            [{"text": "📝 Повідомити про подію"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def build_welcome_message(user: dict) -> str:
    try:
        first = (user.get('first_name') or "").strip()
        last = (user.get('last_name') or "").strip()
        display = (first + (" " + last if last else "")).strip() or "Друже"
        is_premium = user.get('is_premium', False)
        vip_badge = " ✨" if is_premium else ""
        name_html = escape(display)
        msg = (
            "<pre>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</pre>\n"
            f"<b>✨ Ласкаво просимо, {name_html}{vip_badge}!</b>\n\n"
            "<b>На зв'язку адмін каналу!</b>\n"
            "Хочеш поділитися цікавою новиною?\n\n"
            "Відправляй мені інформацію у цей чат, бажано з фото або відео 🔥.\n"
            "Ми обов'язково все розглянемо і, по можливості, опублікуємо!\n\n"
            "<b>НОВИНИ ПУБЛІКУЮТЬСЯ КОНФІДЕНЦІЙНО</b>\n\n"
            "<i>Натисніть кнопку внизу, щоб почати.</i>\n"
            "<pre>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</pre>"
        )
        return msg
    except Exception as e:
        cool_error_handler(e, "build_welcome_message")
        return "Ласкаво просимо! Використайте меню для початку."

# ====== Отправка сообщений ======
def send_message(chat_id, text, reply_markup=None, parse_mode=None, timeout=8):
    if not TOKEN:
        print("[WARN] Попытка отправки сообщения без TOKEN")
        return None
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    if parse_mode:
        payload['parse_mode'] = parse_mode
    try:
        resp = requests.post(url, data=payload, timeout=timeout)
        if not resp.ok:
            MainProtokol(resp.text, 'Помилка надсилання')
        return resp
    except Exception as e:
        cool_error_handler(e, context="send_message")
        MainProtokol(str(e), 'Помилка мережі')
        return None

def _get_reply_markup_for_admin(user_id: int):
    kb = {
        "inline_keyboard": [
            [{"text": "✉️ Відповісти", "callback_data": f"reply_{user_id}"}]
        ]
    }
    return kb

def build_admin_info(message: dict) -> str:
    try:
        user = message.get('from', {}) or {}
        first = (user.get('first_name') or "").strip()
        last = (user.get('last_name') or "").strip()
        username = user.get('username')
        user_id = user.get('id')
        is_premium = user.get('is_premium', None)

        display_name = (first + (" " + last if last else "")).strip() or "Без імені"
        display_html = escape(display_name)

        if username:
            profile_url = f"https://t.me/{username}"
            profile_label = f"@{escape(username)}"
            profile_html = f"<a href=\"{profile_url}\">{profile_label}</a>"
        else:
            profile_url = f"tg://user?id={user_id}"
            profile_label = "Відкрити профіль"
            profile_html = f"<a href=\"{profile_url}\">{escape(profile_label)}</a>"

        msg_id = message.get('message_id', '-')
        msg_date = message.get('date')
        try:
            date_str = datetime.datetime.utcfromtimestamp(int(msg_date)).strftime('%Y-%m-%d %H:%M:%S UTC') if msg_date else '-'
        except Exception:
            date_str = str(msg_date or '-')

        text = message.get('text') or message.get('caption') or ''
        sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        parts = []
        parts.append(f"<pre>{sep}</pre>")
        parts.append("<b>📩 Нова подія</b>")
        parts.append("")

        name_line = f"<b>{display_html}</b>"
        if is_premium:
            name_line += " ✨"
        parts.append(name_line)
        parts.append(f"<b>Профіль:</b> {profile_html}")
        parts.append(f"<b>ID:</b> {escape(str(user_id)) if user_id is not None else '-'}")
        parts.append("")
        parts.append(f"<b>Message ID:</b> {escape(str(msg_id))}")
        parts.append(f"<b>Дата:</b> {escape(str(date_str))}")

        if text:
            display_text = text if len(text) <= 2000 else text[:1997] + "..."
            parts.append("")
            parts.append("<b>Текст / Опис:</b>")
            parts.append("<pre>{}</pre>".format(escape(display_text)))

        parts.append("")
        parts.append("<i>Повідомлення відформатовано для зручного перегляду.</i>")
        parts.append(f"<pre>{sep}</pre>")

        return "\n".join(parts)
    except Exception as e:
        cool_error_handler(e, "build_admin_info")
        return "Нова подія від користувача."

def _post_request(url, data=None, timeout=10):
    try:
        r = requests.post(url, data=data, timeout=timeout)
        if not r.ok:
            MainProtokol(f"Request failed: {url} -> {r.status_code} {r.text}", ts='WARN')
        return r
    except Exception as e:
        MainProtokol(f"Network error for {url}: {str(e)}", ts='ERROR')
        return None

def forward_admin_message_to_user(user_id: int, admin_msg: dict):
    try:
        if not user_id:
            return False
        
        caption = admin_msg.get('caption') or admin_msg.get('text') or ""
        safe_caption = escape(caption) if caption else None

        if 'photo' in admin_msg:
            file_id = admin_msg['photo'][-1].get('file_id')
            url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
            payload = {"chat_id": user_id, "photo": file_id}
            if safe_caption:
                payload["caption"] = f"💬 Відповідь адміністратора:\n<pre>{safe_caption}</pre>"
                payload["parse_mode"] = "HTML"
            else:
                payload["caption"] = "💬 Відповідь адміністратора"
            _post_request(url, data=payload)
            return True

        if 'video' in admin_msg:
            file_id = admin_msg['video'].get('file_id')
            url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
            payload = {"chat_id": user_id, "video": file_id}
            if safe_caption:
                payload["caption"] = f"💬 Відповідь адміністратора:\n<pre>{safe_caption}</pre>"
                payload["parse_mode"] = "HTML"
            else:
                payload["caption"] = "💬 Відповідь адміністратора"
            _post_request(url, data=payload)
            return True

        if 'document' in admin_msg:
            file_id = admin_msg['document'].get('file_id')
            filename = admin_msg.get('document', {}).get('file_name', 'документ')
            url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
            payload = {"chat_id": user_id, "document": file_id}
            if safe_caption:
                payload["caption"] = f"💬 Відповідь адміністратора:\n<pre>{safe_caption}</pre>"
                payload["parse_mode"] = "HTML"
            else:
                payload["caption"] = f"💬 Відповідь адміністратора — {escape(filename)}"
            _post_request(url, data=payload)
            return True

        if caption:
            send_message(user_id, f"💬 Відповідь адміністратора:\n<pre>{escape(caption)}</pre>", parse_mode="HTML")
            return True

        send_message(user_id, "💬 Відповідь адміністратора (без тексту).")
        return True
    except Exception as e:
        cool_error_handler(e, "forward_admin_message_to_user")
        return False

# ====== Глобальное состояние ======
waiting_for_admin = {}
user_messages = {}  # chat_id -> list of messages

# ====== Flask App ======
app = Flask(__name__)

@app.errorhandler(Exception)
def flask_global_error_handler(e):
    cool_error_handler(e, context="Flask global error handler")
    return "Внутрішня помилка сервера.", 500

@app.route("/webhook", methods=["POST"])
def webhook():
    global waiting_for_admin, user_messages
    try:
        data_raw = request.get_data(as_text=True)
        update = json.loads(data_raw)

        # CALLBACK HANDLING
        if 'callback_query' in update:
            call = update['callback_query']
            chat_id = call['from']['id']
            data = call.get('data', '')

            if data.startswith("reply_") and chat_id == ADMIN_ID:
                try:
                    user_id = int(data.split("_", 1)[1])
                    waiting_for_admin[ADMIN_ID] = user_id
                    send_message(
                        ADMIN_ID,
                        f"✍️ Введіть відповідь для користувача {user_id} (текст або файл):"
                    )
                except Exception as e:
                    cool_error_handler(e, context="webhook: callback_query reply_")
                    MainProtokol(str(e), 'Помилка callback reply')

            return "ok", 200

        # MESSAGE HANDLING
        if 'message' in update:
            message = update['message']
            chat = message.get('chat') or {}
            frm = message.get('from') or {}
            chat_id = chat.get('id')
            from_id = frm.get('id')
            text = message.get('text', '')

            # Ответ администратора пользователю
            if from_id == ADMIN_ID and ADMIN_ID in waiting_for_admin:
                user_to_send = waiting_for_admin.pop(ADMIN_ID, None)
                success = False
                if user_to_send:
                    success = forward_admin_message_to_user(user_to_send, message)
                if success:
                    send_message(ADMIN_ID, f"✅ Повідомлення надіслано користувачу {user_to_send}.", reply_markup=get_reply_buttons())
                else:
                    send_message(ADMIN_ID, f"❌ Не вдалося надіслати повідомлення користувачу {user_to_send}.", reply_markup=get_reply_buttons())
                return "ok", 200

            # /start команда
            if text == '/start':
                send_chat_action(chat_id, 'typing')
                time.sleep(0.25)
                user = message.get('from', {})
                welcome = build_welcome_message(user)
                send_message(
                    chat_id,
                    welcome,
                    reply_markup=get_reply_buttons(),
                    parse_mode='HTML'
                )
            # Кнопка "📝 Повідомити про подію"
            elif text == "📝 Повідомити про подію":
                # Инициализируем сбор сообщений
                user_messages[chat_id] = []
                send_message(
                    chat_id,
                    "📝 Надсилайте вашу інформацію (текст, фото, відео, документи).\n\n"
                    "Натисніть 'Готово' коли закінчите.",
                    reply_markup={
                        "keyboard": [
                            [{"text": "✅ Готово"}],
                            [{"text": "❌ Скасувати"}]
                        ],
                        "resize_keyboard": True,
                        "one_time_keyboard": False
                    }
                )
            # Готово - отправляем все собранные сообщения админу
            elif text == "✅ Готово":
                send_message(chat_id, "✅ Дякуємо! Ваша інформація відправлена адміністратору.", reply_markup=get_reply_buttons())
                
                # Отправляем информацию о пользователе
                if chat_id in user_messages and user_messages[chat_id]:
                    first_msg = user_messages[chat_id][0]
                    admin_info = build_admin_info(first_msg)
                    orig_user_id = first_msg.get('from', {}).get('id')
                    reply_markup = _get_reply_markup_for_admin(orig_user_id)
                    send_message(ADMIN_ID, admin_info, reply_markup=reply_markup, parse_mode="HTML")
                    
                    # Отправляем все собранные медиа
                    for msg in user_messages[chat_id]:
                        send_collected_message(ADMIN_ID, msg)
                    
                    # Очищаем список
                    user_messages.pop(chat_id, None)
            # Скасувати
            elif text == "❌ Скасувати":
                send_message(chat_id, "❌ Скасовано.", reply_markup=get_reply_buttons())
                user_messages.pop(chat_id, None)
            # Собираем все остальные сообщения
            else:
                if from_id != ADMIN_ID and chat_id in user_messages:
                    user_messages[chat_id].append(message)
                    send_message(
                        chat_id,
                        "✅ Додано. Продовжуйте надсилати або натисніть ✅ Готово.",
                        reply_markup={
                            "keyboard": [
                                [{"text": "✅ Готово"}],
                                [{"text": "❌ Скасувати"}]
                            ],
                            "resize_keyboard": True,
                            "one_time_keyboard": False
                        }
                    )

        return "ok", 200

    except Exception as e:
        cool_error_handler(e, context="webhook - outer")
        MainProtokol(str(e), 'Помилка webhook')
        return "ok", 200

def send_collected_message(chat_id, message: dict):
    """Отправляет собранное сообщение (фото, видео, текст и т.д.) админу"""
    try:
        if 'photo' in message:
            file_id = message['photo'][-1].get('file_id')
            caption = message.get('caption', '')
            url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
            payload = {"chat_id": chat_id, "photo": file_id}
            if caption:
                payload["caption"] = escape(caption)
            requests.post(url, data=payload, timeout=10)
            return

        if 'video' in message:
            file_id = message['video'].get('file_id')
            caption = message.get('caption', '')
            url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
            payload = {"chat_id": chat_id, "video": file_id}
            if caption:
                payload["caption"] = escape(caption)
            requests.post(url, data=payload, timeout=10)
            return

        if 'document' in message:
            file_id = message['document'].get('file_id')
            caption = message.get('caption', '')
            url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
            payload = {"chat_id": chat_id, "document": file_id}
            if caption:
                payload["caption"] = escape(caption)
            requests.post(url, data=payload, timeout=10)
            return

        if 'audio' in message:
            file_id = message['audio'].get('file_id')
            caption = message.get('caption', '')
            url = f"https://api.telegram.org/bot{TOKEN}/sendAudio"
            payload = {"chat_id": chat_id, "audio": file_id}
            if caption:
                payload["caption"] = escape(caption)
            requests.post(url, data=payload, timeout=10)
            return

        if 'voice' in message:
            file_id = message['voice'].get('file_id')
            url = f"https://api.telegram.org/bot{TOKEN}/sendVoice"
            payload = {"chat_id": chat_id, "voice": file_id}
            requests.post(url, data=payload, timeout=10)
            return

        if 'text' in message:
            text = message['text']
            send_message(chat_id, f"<pre>{escape(text)}</pre>", parse_mode="HTML")
            return

    except Exception as e:
        MainProtokol(f"Error sending collected message: {str(e)}", ts='ERROR')

@app.route('/', methods=['GET'])
def index():
    try:
        MainProtokol('Відвідання сайту')
        return "Бот працює ✅", 200
    except Exception as e:
        cool_error_handler(e, context="index route")
        return "Error", 500

if __name__ == "__main__":
    try:
        threading.Thread(target=time_debugger, daemon=True).start()
    except Exception as e:
        cool_error_handler(e, context="main: start time_debugger")
    
    try:
        print(f"\n[INFO] Запуск Flask на 0.0.0.0:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False)
    except Exception as e:
        cool_error_handler(e, context="main: app.run")
