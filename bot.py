import os
import sqlite3
import secrets
import string
import requests
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot import types

# ===== CONFIG =====
REAL_API_URL = "https://info-ob49.onrender.com/api/account/"
BOT_TOKEN = "8703834112:AAEmaLXHKV53PeS28M05_KF7msIZ9r62nKA"
ADMIN_IDS = [7424107874]
ADMIN_USERNAME = "@zadxpr0"
CHANNELS = ["@zadxprootziv", "@zadxproooo"]
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.environ.get("PORT", 5000))
RENDER_URL = "https://bot-telegram-api-bot.onrender.com"

# ===== DATABASE =====
DB_FILE = "/tmp/keys.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            username TEXT,
            created_at TEXT,
            expires_at TEXT,
            max_requests INTEGER DEFAULT -1,
            used_requests INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def generate_key(length=32):
    chars = string.ascii_letters + string.digits
    return "FF-" + "".join(secrets.choice(chars) for _ in range(length))

def create_key(user_id, username, days, max_requests=-1):
    key = generate_key()
    now = datetime.now()
    expires = now + timedelta(days=days)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO api_keys (key, user_id, username, created_at, expires_at, max_requests)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (key, user_id, username, now.isoformat(), expires.isoformat(), max_requests))
    conn.commit()
    conn.close()
    return key, expires

def validate_key(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, "Key вуҷуд надорад"
    _, _, _, _, created_at, expires_at, max_requests, used_requests, is_active = row
    if not is_active:
        return False, "Key ғайрифаъол аст"
    if datetime.now() > datetime.fromisoformat(expires_at):
        return False, "Key тамом шудааст"
    if max_requests != -1 and used_requests >= max_requests:
        return False, "Лимити request тамом шуд"
    return True, "OK"

def increment_usage(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE api_keys SET used_requests = used_requests + 1 WHERE key = ?", (key,))
    conn.commit()
    conn.close()

def get_key_info(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row

def revoke_key(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE api_keys SET is_active = 0 WHERE key = ?", (key,))
    conn.commit()
    conn.close()

def get_user_keys(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key, expires_at, used_requests, max_requests, is_active FROM api_keys WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_keys():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT key, username, expires_at, used_requests, is_active FROM api_keys ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    return rows

# ===== FLASK =====
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "✅ API is running!"})

@app.route("/api/player", methods=["GET"])
def player_info():
    key = request.args.get("key")
    uid = request.args.get("uid")
    region = request.args.get("region", "IND")

    if not key:
        return jsonify({"error": "Key нест"}), 401
    if not uid:
        return jsonify({"error": "UID нест"}), 400

    valid, reason = validate_key(key)
    if not valid:
        return jsonify({"error": reason}), 403

    try:
        real_response = requests.get(
            REAL_API_URL,
            params={"uid": uid, "region": region},
            timeout=10
        )
        increment_usage(key)
        return jsonify(real_response.json()), real_response.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "API ҷавоб надод"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/check", methods=["GET"])
def check_key_api():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "Key нест"}), 401

    valid, reason = validate_key(key)
    info = get_key_info(key)
    if not info:
        return jsonify({"valid": False, "reason": "Key нест"}), 404

    _, _, user_id, username, created_at, expires_at, max_req, used_req, is_active = info
    expires = datetime.fromisoformat(expires_at)
    remaining = (expires - datetime.now()).days

    return jsonify({
        "valid": valid,
        "reason": reason,
        "expires_in_days": max(0, remaining),
        "used_requests": used_req,
        "max_requests": max_req if max_req != -1 else "unlimited"
    })

# ===== BOT =====
bot = telebot.TeleBot(BOT_TOKEN)
user_uid_state = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def check_subscription(user_id):
    not_subscribed = []
    for channel in CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    return not_subscribed

def send_subscribe_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    for ch in CHANNELS:
        markup.add(types.InlineKeyboardButton(f"📢 {ch}", url=f"https://t.me/{ch[1:]}"))
    markup.add(types.InlineKeyboardButton("✅ Санҷидан", callback_data="check_sub"))
    bot.send_message(chat_id, "❗️ *Барои истифода аввал ба каналҳо обуна шав:*",
                     parse_mode="Markdown", reply_markup=markup)

def send_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔍 Санҷиши API", callback_data="check_api"))
    markup.add(types.InlineKeyboardButton("🛒 Хариди API", callback_data="buy_api"))
    bot.send_message(chat_id, "🎮 *Free Fire API Bot*\n\nЯке аз хизматҳоро интихоб кун:",
                     parse_mode="Markdown", reply_markup=markup)

def send_admin_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💎 API сохтан", callback_data="admin_newkey"))
    markup.add(types.InlineKeyboardButton("📋 Ҳамаи Key ҳо", callback_data="admin_allkeys"))
    markup.add(types.InlineKeyboardButton("❌ Key хомӯш кун", callback_data="admin_revoke"))
    bot.send_message(chat_id, "👑 *Панели Админ*\n\nЯке аз амалҳоро интихоб кун:",
                     parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=["start"])
def start(msg):
    if is_admin(msg.from_user.id):
        send_admin_menu(msg.chat.id)
        return
    not_sub = check_subscription(msg.from_user.id)
    if not_sub:
        send_subscribe_message(msg.chat.id)
    else:
        send_main_menu(msg.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "check_sub":
        not_sub = check_subscription(user_id)
        if not_sub:
            bot.answer_callback_query(call.id, "❌ Ҳоло обуна нашудаӣ!", show_alert=True)
        else:
            bot.delete_message(chat_id, msg_id)
            send_main_menu(chat_id)

    elif call.data == "check_api":
        not_sub = check_subscription(user_id)
        if not_sub:
            bot.answer_callback_query(call.id, "❌ Аввал обуна шав!", show_alert=True)
            return
        user_uid_state[user_id] = "waiting_uid"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.edit_message_text(
            "🔍 *Санҷиши API*\n\nАйди Free Fire худро фирист:",
            chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "buy_api":
        not_sub = check_subscription(user_id)
        if not_sub:
            bot.answer_callback_query(call.id, "❌ Аввал обуна шав!", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👤 Админ", url=f"https://t.me/{ADMIN_USERNAME[1:]}"))
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.edit_message_text(
            "🛒 *Хариди API*\n\nБарои харидан ба админ муроҷиат кунед! ✅",
            chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "back_menu":
        if user_id in user_uid_state:
            del user_uid_state[user_id]
        bot.delete_message(chat_id, msg_id)
        if is_admin(user_id):
            send_admin_menu(chat_id)
        else:
            send_main_menu(chat_id)

    elif call.data == "admin_newkey":
        user_uid_state[user_id] = "admin_waiting_key_info"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.edit_message_text(
            "💎 *API сохтан*\n\nДар ин формат нависед:\n"
            "`@username 1d`\n`@username 10d`\n`@username 1m`\n"
            "`@username 1d 100` — бо лимити request",
            chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "admin_allkeys":
        keys = get_all_keys()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        if not keys:
            bot.edit_message_text("📋 Ҳеч key нест.", chat_id, msg_id, reply_markup=markup)
            return
        now = datetime.now()
        text = "📋 *Ҳамаи Key ҳо:*\n\n"
        for k, username, expires_at, used, active in keys:
            expires = datetime.fromisoformat(expires_at)
            remaining = (expires - now).days
            status = "✅" if active and remaining >= 0 else "❌"
            short_key = k[:15] + "..."
            text += f"{status} `{short_key}` — @{username} — {max(0,remaining)}р — {used} req\n"
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "admin_revoke":
        user_uid_state[user_id] = "admin_waiting_revoke"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.edit_message_text("❌ *Key хомӯш кун*\n\nKey иро фирист:",
                              chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda msg: True)
def handle_messages(msg):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    text = msg.text

    if user_uid_state.get(user_id) == "admin_waiting_key_info" and is_admin(user_id):
        del user_uid_state[user_id]
        parts = text.strip().split()
        if len(parts) < 2:
            bot.reply_to(msg, "❌ Формат: @username 1d")
            send_admin_menu(chat_id)
            return
        target = parts[0]
        period = parts[1]
        max_req = int(parts[2]) if len(parts) > 2 else -1
        if period == "1d":
            days, label = 1, "1 рӯз"
        elif period == "10d":
            days, label = 10, "10 рӯз"
        elif period == "1m":
            days, label = 30, "1 моҳ"
        elif period.endswith("d") and period[:-1].isdigit():
            days = int(period[:-1])
            label = f"{days} рӯз"
        else:
            bot.reply_to(msg, "❌ Вақт дуруст нест!")
            send_admin_menu(chat_id)
            return
        username = target[1:] if target.startswith("@") else target
        key, expires = create_key(0, username, days, max_req)
        req_text = f"{max_req} request" if max_req != -1 else "Беҳад"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.send_message(chat_id,
            f"✅ *Key сохта шуд!*\n\n"
            f"👤 Барои: `{target}`\n"
            f"🔑 Key:\n`{key}`\n\n"
            f"⏱ Вақт: *{label}*\n"
            f"📊 Request: *{req_text}*\n"
            f"📅 Тамом: `{expires.strftime('%Y-%m-%d %H:%M')}`\n\n"
            f"🌐 *Истифода:*\n"
            f"`{RENDER_URL}/api/player?key={key}&uid=UID&region=IND`",
            parse_mode="Markdown", reply_markup=markup)

    elif user_uid_state.get(user_id) == "admin_waiting_revoke" and is_admin(user_id):
        del user_uid_state[user_id]
        key = text.strip()
        revoke_key(key)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
        bot.send_message(chat_id, f"✅ Key хомӯш шуд:\n`{key}`",
                         parse_mode="Markdown", reply_markup=markup)

    elif user_uid_state.get(user_id) == "waiting_uid":
        del user_uid_state[user_id]
        uid = text.strip()
        if not uid.isdigit():
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
            bot.send_message(chat_id, "❌ UID танҳо рақам аст!", reply_markup=markup)
            return
        wait_msg = bot.send_message(chat_id, "⏳ Маълумот меёбам...")
        try:
            resp = requests.get(REAL_API_URL, params={"uid": uid, "region": "IND"}, timeout=10)
            data = resp.json()
            basic = data.get("basicInfo", {})
            clan = data.get("clanBasicInfo", {})
            name = basic.get("nickname", "Номаълум")
            level = basic.get("level", "?")
            region = basic.get("region", "?")
            rank = basic.get("rank", "?")
            liked = basic.get("liked", "?")
            has_ep = "✅" if basic.get("hasElitePass") else "❌"
            clan_name = clan.get("clanName", "Нест")
            result_text = (
                f"🎮 *Free Fire маълумот*\n\n"
                f"👤 Ном: `{name}`\n"
                f"🆔 UID: `{uid}`\n"
                f"⭐️ Сатҳ: `{level}`\n"
                f"🌍 Минтақа: `{region}`\n"
                f"🏆 Ранг: `{rank}`\n"
                f"❤️ Лайк: `{liked}`\n"
                f"💎 Elite Pass: {has_ep}\n"
                f"🏰 Клан: `{clan_name}`\n\n"
                f"⚠️ *Лутфан айдитро фирист*"
            )
            bot.delete_message(chat_id, wait_msg.message_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
            sent = bot.send_message(chat_id, result_text, parse_mode="Markdown", reply_markup=markup)

            def delete_later():
                time.sleep(10)
                try:
                    bot.delete_message(chat_id, sent.message_id)
                    send_main_menu(chat_id)
                except:
                    pass
            threading.Thread(target=delete_later).start()

        except Exception as e:
            bot.delete_message(chat_id, wait_msg.message_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Бозгашт", callback_data="back_menu"))
            bot.send_message(chat_id, f"❌ Хато: {str(e)}", reply_markup=markup)

# ===== ОҒОЗ =====
if __name__ == "__main__":
    init_db()
    print("✅ Bot started!")
    t = threading.Thread(target=lambda: app.run(host=SERVER_HOST, port=SERVER_PORT, use_reloader=False))
    t.daemon = True
    t.start()
    bot.infinity_polling()
