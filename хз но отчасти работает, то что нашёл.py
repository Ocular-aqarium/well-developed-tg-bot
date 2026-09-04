import telebot
from telebot import types
from telebot.types import MessageEntity
import random, threading, json, os

BOT_TOKEN = "8848082883:AAF7YGVg_nzSL0XEGt4DQqdx_QuMnu7tcqQ"
bot = telebot.TeleBot(BOT_TOKEN)

OWNER_ID = 7730444670

# ══════════════════════════════════════════════════
#  БАЗА ПОЛЬЗОВАТЕЛЕЙ
# ══════════════════════════════════════════════════

USERS_FILE = "users.json"

def load_users() -> set:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

known_users: set = load_users()

def register_user(user_id: int):
    if user_id not in known_users:
        known_users.add(user_id)
        save_users(known_users)

# ══════════════════════════════════════════════════
#  СОСТОЯНИЯ
# ══════════════════════════════════════════════════

# Режим стикеров/эмодзи: "id" (по умолчанию) или "conv"
# Применяется ко всем пользователям, включая владельца
sticker_mode: dict[int, str] = {}

# Лимит: сколько сообщений ждут ответа
pending_count: dict[int, int] = {}
MESSAGE_LIMIT = 6

def get_pending(uid: int) -> int:
    return pending_count.get(uid, 0)

def increment_pending(uid: int):
    pending_count[uid] = pending_count.get(uid, 0) + 1

def reset_pending(uid: int):
    pending_count[uid] = 0

def check_limit(message) -> bool:
    """True — можно отправлять. False — лимит исчерпан, уже ответил пользователю."""
    uid = message.from_user.id
    if uid == OWNER_ID:
        return True
    if get_pending(uid) >= MESSAGE_LIMIT:
        bot.reply_to(
            message,
            "Вы не можете отправить больше 6 сообщений, пока автор не ответит — во избежание спама 🙏"
        )
        return False
    return True

# message_id сообщения у владельца -> user_id отправителя
user_map: dict[int, int] = {}

# bot_message_id запроса подтверждения -> данные для пересылки
pending_media: dict[int, dict] = {}

# ══════════════════════════════════════════════════
#  ТЕКСТЫ
# ══════════════════════════════════════════════════

HOW_TO_CONTACT_TEXT = (
    "Со мной можно связаться прямо через этого бота 📨\n\n"
    "Просто напишите любое текстовое сообщение — бот спросит подтверждение и перешлёт его мне с вашим @юзернеймом.\n\n"
    "Фото, видео, аудио и гифки тоже можно отправить: бот сначала спросит подтверждение, "
    "и только после вашего «да» перешлёт материал.\n\n"
    "Я постараюсь ответить — ответ придёт вам сюда, в этот же чат."
)

# ══════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════════════════

def main_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Это можно скрыть кнопкой рядом с 📎"))
    markup.add(
        types.KeyboardButton("Рандомайзер от 1 до 100"),
        types.KeyboardButton("Рандомайзер от 1 до 1000"),
    )
    return markup

def confirm_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("да", callback_data="media_yes"),
        types.InlineKeyboardButton("нет", callback_data="media_no"),
    )
    return markup

# ══════════════════════════════════════════════════
#  ХЕЛПЕРЫ
# ══════════════════════════════════════════════════

def ask_confirm(message, data: dict):
    """Отправить запрос подтверждения и сохранить данные."""
    sent = bot.send_message(message.chat.id, "Отправить автору?", reply_markup=confirm_markup())
    pending_media[sent.message_id] = data

def get_username(message) -> str:
    return (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "(без username)"
    )

def send_to_owner(data: dict) -> "telebot.types.Message | None":
    """
    Отправить контент владельцу по данным из pending_media.
    Возвращает последнее отправленное сообщение (для user_map).
    """
    uid      = data["user_id"]
    username = data["username"]
    caption  = data.get("caption", "")
    mtype    = data["type"]

    header = f"От: {username}\nID: {uid}"
    if caption:
        header += f"\n\n{caption}"

    sent = None

    if mtype == "text":
        bot.send_message(OWNER_ID, f"📩 Новое сообщение\n\nОт: {username}\nID: {uid}")
        sent = bot.send_message(
            OWNER_ID,
            data["text"],
            entities=data.get("entities") or None
        )

    elif mtype == "photo":
        sent = bot.send_photo(OWNER_ID, data["file_id"], caption=header)

    elif mtype == "video":
        sent = bot.send_video(OWNER_ID, data["file_id"], caption=header)

    elif mtype == "audio":
        sent = bot.send_audio(OWNER_ID, data["file_id"], caption=header)

    elif mtype == "voice":
        sent = bot.send_voice(OWNER_ID, data["file_id"], caption=header)

    elif mtype == "animation":
        bot.send_message(OWNER_ID, f"🎞 Анимация\n\n{header}")
        sent = bot.send_animation(OWNER_ID, data["file_id"])

    elif mtype == "document":
        sent = bot.send_document(OWNER_ID, data["file_id"], caption=header)

    elif mtype == "video_note":
        bot.send_message(OWNER_ID, f"⭕ Кружок\n\n{header}")
        sent = bot.send_video_note(OWNER_ID, data["file_id"])

    elif mtype == "sticker":
        bot.send_message(OWNER_ID, f"🎭 Стикер\n\n{header}")
        sent = bot.send_sticker(OWNER_ID, data["file_id"])

    return sent

# ══════════════════════════════════════════════════
#  ХЕЛПЕР: ПОКАЗАТЬ ID СТИКЕРА
#  Используется и для владельца, и для пользователей
# ══════════════════════════════════════════════════

def reply_sticker_id(message):
    """Ответить сообщением с file_id и custom_emoji_id стикера."""
    sticker = message.sticker
    text = (
        "<b>ID стикера:</b>\n\n"
        f"<code>{sticker.file_id}</code>\n\n"
        "[Нажмите, чтобы скопировать]"
    )
    if getattr(sticker, "custom_emoji_id", None):
        text += (
            f"\n\n<b>custom_emoji_id:</b>\n"
            f"<code>{sticker.custom_emoji_id}</code>\n"
            "(премиум-эмодзи)"
        )
    bot.reply_to(message, text, parse_mode="HTML")

# ══════════════════════════════════════════════════
#  КОМАНДЫ
# ══════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def handle_start(message):
    register_user(message.from_user.id)
    bot.send_sticker(
        message.chat.id,
        "CAACAgIAAxkBAAEEWHhqID0xHoSmkqy57Yb-_3UteKjdBwACUgADwIUfGqDRfkE7Amw2OwQ"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("»»»", callback_data="next_step"))
    bot.send_message(
        message.chat.id,
        "Привки!\n\nДанный бот экспериментальный, и скорее создан для демонстрации "
        "функционала, так что не относитесь к нему серьёзно",
        reply_markup=markup
    )

# /id — переключить в режим показа ID стикеров/эмодзи (работает для всех, включая владельца)
@bot.message_handler(commands=["id", "getid"])
def handle_cmd_id(message):
    register_user(message.from_user.id)
    sticker_mode[message.from_user.id] = "id"
    bot.reply_to(message, "Режим ID активен: стикеры и премиум-эмодзи будут показывать свой ID.")

# /conv — стикеры/эмодзи пересылаются владельцу (для обычных пользователей)
@bot.message_handler(commands=["conv"])
def handle_cmd_conv(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        bot.reply_to(message, "⚠️ Режим /conv недоступен для автора — стикеры и так приходят напрямую.")
        return
    sticker_mode[message.from_user.id] = "conv"
    bot.reply_to(message, "Режим /conv активен: стикеры и эмодзи будут пересылаться автору.")

# ══════════════════════════════════════════════════
#  CALLBACK HANDLERS
# ══════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda call: call.data == "next_step")
def handle_next_step(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "да", callback_data="answer_yes",
            style="success",
            icon_custom_emoji_id="5373043145728627550"
        ),
        types.InlineKeyboardButton(
            "нет", callback_data="answer_no",
            style="danger",
            icon_custom_emoji_id="5195071168545043110"
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "что-то полезное", callback_data="answer_useful",
            style="primary",
            icon_custom_emoji_id="5321239543716781153"
        ),
    )
    sent = bot.send_message(
        call.message.chat.id,
        "хотите узнать как работают тг-боты, и что скрыто по ту сторону?",
        reply_markup=markup
    )
    def pin_later():
        try:
            bot.pin_chat_message(call.message.chat.id, sent.message_id, disable_notification=True)
        except Exception as e:
            print(f"Не удалось закрепить: {e}")
    threading.Timer(5.0, pin_later).start()

@bot.callback_query_handler(func=lambda call: call.data == "answer_yes")
def handle_yes(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, HOW_TO_CONTACT_TEXT)

@bot.callback_query_handler(func=lambda call: call.data == "answer_no")
def handle_no(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Ну как хочешь")

@bot.callback_query_handler(func=lambda call: call.data == "answer_useful")
def handle_useful(call):
    bot.answer_callback_query(call.id)
    sent = bot.send_message(
        call.message.chat.id,
        "https://t.me/addstickers/forttochka_by_fStikBot",
        reply_markup=main_reply_keyboard()
    )
    try:
        bot.set_message_reaction(
            call.message.chat.id, sent.message_id,
            reaction=[types.ReactionTypeEmoji("🙏")], is_big=False
        )
    except Exception as e:
        print(f"Реакция: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reroll_"))
def handle_reroll(call):
    bot.answer_callback_query(call.id)
    max_val = int(call.data.split("_")[1])
    num = random.randint(1, max_val)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄", callback_data=f"reroll_{max_val}"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Выпало: {num}",
        reply_markup=markup
    )

# ── Подтверждение: ДА ─────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "media_yes")
def handle_confirm_yes(call):
    bot.answer_callback_query(call.id)
    bot_msg_id = call.message.message_id
    data = pending_media.pop(bot_msg_id, None)

    if not data:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=bot_msg_id,
            text="⚠️ Данные истекли, отправьте снова"
        )
        return

    sent = send_to_owner(data)
    if sent:
        user_map[sent.message_id] = data["user_id"]
        increment_pending(data["user_id"])

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=bot_msg_id,
        text="Отправлено ✅"
    )

# ── Подтверждение: НЕТ ───────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "media_no")
def handle_confirm_no(call):
    bot.answer_callback_query(call.id)
    pending_media.pop(call.message.message_id, None)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Отправка отменена"
    )

# ══════════════════════════════════════════════════
#  МЕДИА-ХЕНДЛЕРЫ
#  ВАЖНО: animation должен идти ДО document
# ══════════════════════════════════════════════════

@bot.message_handler(content_types=["animation"])
def handle_animation(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "animation",
        "file_id": message.animation.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": (message.caption or "").strip(),
    })

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "photo",
        "file_id": message.photo[-1].file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": (message.caption or "").replace("/llm", "").strip(),
    })

@bot.message_handler(content_types=["video"])
def handle_video(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "video",
        "file_id": message.video.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": (message.caption or "").strip(),
    })

@bot.message_handler(content_types=["audio"])
def handle_audio(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "audio",
        "file_id": message.audio.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": (message.caption or "").strip(),
    })

@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "voice",
        "file_id": message.voice.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": "",
    })

@bot.message_handler(content_types=["document"])
def handle_document(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "document",
        "file_id": message.document.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": (message.caption or "").strip(),
    })

@bot.message_handler(content_types=["video_note"])
def handle_video_note(message):
    register_user(message.from_user.id)
    if message.from_user.id == OWNER_ID:
        return
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "video_note",
        "file_id": message.video_note.file_id,
        "user_id": message.from_user.id,
        "username": get_username(message),
        "caption": "",
    })

# ══════════════════════════════════════════════════
#  СТИКЕРЫ — единый хендлер для всех
# ══════════════════════════════════════════════════

@bot.message_handler(content_types=["sticker"])
def handle_sticker(message):
    register_user(message.from_user.id)
    uid = message.from_user.id

    # Режим по умолчанию — "id" (показывать ID)
    mode = sticker_mode.get(uid, "id")

    if mode == "id":
        # Показываем ID стикера — работает для всех, включая владельца
        reply_sticker_id(message)
        return

    # Режим "conv" — только для обычных пользователей (не владельца)
    # Владелец в этот режим попасть не может (команда /conv заблокирована для него)
    if not check_limit(message):
        return
    ask_confirm(message, {
        "type": "sticker",
        "file_id": message.sticker.file_id,
        "user_id": uid,
        "username": get_username(message),
        "caption": "",
    })

# ══════════════════════════════════════════════════
#  ТЕКСТОВЫЕ ХЕНДЛЕРЫ
#  Порядок критически важен для telebot
# ══════════════════════════════════════════════════

# ── 1. Кнопки нижнего меню ────────────────────────
@bot.message_handler(func=lambda m: m.text == "Это можно скрыть кнопкой рядом с 📎")
def handle_info_button(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "Рандомайзер от 1 до 100")
def handle_rand100(message):
    num = random.randint(1, 100)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄", callback_data="reroll_100"))
    bot.send_message(message.chat.id, f"Выпало: {num}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "Рандомайзер от 1 до 1000")
def handle_rand1000(message):
    num = random.randint(1, 1000)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄", callback_data="reroll_1000"))
    bot.send_message(message.chat.id, f"Выпало: {num}", reply_markup=markup)

# ── 2. Рассылка владельца ─────────────────────────
@bot.message_handler(
    func=lambda m: (
        m.from_user.id == OWNER_ID
        and m.text is not None
        and m.text.startswith("/broadcast_nosassy")
    ),
    content_types=["text"]
)
def handle_broadcast_text(message):
    text = message.text[len("/broadcast_nosassy"):].strip()
    if not text:
        bot.reply_to(message, "Нечего рассылать")
        return
    ok, fail = 0, 0
    for uid in list(known_users):
        try:
            bot.send_message(uid, text)
            ok += 1
        except Exception as e:
            print(f"Не удалось отправить {uid}: {e}")
            fail += 1
    bot.reply_to(message, f"✅ Отправлено: {ok}\n❌ Ошибок: {fail}")

@bot.message_handler(
    func=lambda m: (
        m.from_user.id == OWNER_ID
        and m.caption is not None
        and m.caption.startswith("/broadcast_nosassy")
    ),
    content_types=["photo"]
)
def handle_broadcast_photo(message):
    text = message.caption[len("/broadcast_nosassy"):].strip()
    photo_id = message.photo[-1].file_id
    ok, fail = 0, 0
    for uid in list(known_users):
        try:
            bot.send_photo(uid, photo_id, caption=text)
            ok += 1
        except Exception as e:
            print(f"Не удалось отправить {uid}: {e}")
            fail += 1
    bot.reply_to(message, f"✅ Отправлено: {ok}\n❌ Ошибок: {fail}")

# ── 3. Ответ владельца пользователю ──────────────
@bot.message_handler(
    func=lambda m: (
        m.from_user.id == OWNER_ID
        and m.reply_to_message is not None
    ),
    content_types=["text"]
)
def owner_reply(message):
    replied_id = message.reply_to_message.message_id
    if replied_id not in user_map:
        return
    target_user = user_map[replied_id]
    reset_pending(target_user)
    bot.send_message(target_user, f"Ответ:\n\n{message.text}")
    bot.reply_to(message, "Отправлено")

# ── 4. Премиум-эмодзи в режиме "id" ──────────────
@bot.message_handler(
    content_types=["text"],
    func=lambda m: (
        m.entities is not None
        and any(e.type == "custom_emoji" for e in m.entities)
        and sticker_mode.get(m.from_user.id, "id") == "id"
    )
)
def handle_premium_emoji_id_mode(message):
    register_user(message.from_user.id)
    uid = message.from_user.id

    # Показываем ID эмодзи
    emoji_entities = [e for e in message.entities if e.type == "custom_emoji"]
    response_text = "Обнаруженные премиум-эмодзи:\n\n"
    utf16_text = message.text.encode("utf-16-le")
    new_entities = []

    for entity in emoji_entities:
        start = entity.offset * 2
        end   = (entity.offset + entity.length) * 2
        emoji_char = utf16_text[start:end].decode("utf-16-le")
        emoji_offset = len(response_text.encode("utf-16-le")) // 2
        response_text += f"{emoji_char} - {entity.custom_emoji_id}\n\n[Нажмите чтобы скопировать]\n\n"
        id_str = str(entity.custom_emoji_id)
        id_offset = emoji_offset + (len(emoji_char.encode("utf-16-le")) // 2) + 3
        new_entities.append(MessageEntity(
            type="custom_emoji",
            offset=emoji_offset,
            length=len(emoji_char.encode("utf-16-le")) // 2,
            custom_emoji_id=entity.custom_emoji_id
        ))
        new_entities.append(MessageEntity(
            type="code",
            offset=id_offset,
            length=len(id_str.encode("utf-16-le")) // 2
        ))

    bot.send_message(
        chat_id=message.chat.id,
        text=response_text.strip(),
        entities=new_entities,
        reply_to_message_id=message.message_id
    )

    # Предлагаем переслать владельцу — только не владельцу самому
    if uid != OWNER_ID and check_limit(message):
        ask_confirm(message, {
            "type": "text",
            "text": message.text,
            "entities": message.entities,
            "user_id": uid,
            "username": get_username(message),
        })

# ── 5. Catch-all: любой текст от пользователя (не владельца) ────
@bot.message_handler(
    content_types=["text"],
    func=lambda m: m.from_user.id != OWNER_ID
)
def handle_any_text(message):
    register_user(message.from_user.id)

    # Кнопки меню уже обработаны выше — на всякий случай
    if message.text in (
        "Это можно скрыть кнопкой рядом с 📎",
        "Рандомайзер от 1 до 100",
        "Рандомайзер от 1 до 1000",
    ):
        return

    if not check_limit(message):
        return

    ask_confirm(message, {
        "type": "text",
        "text": message.text,
        "entities": message.entities,
        "user_id": message.from_user.id,
        "username": get_username(message),
    })


if __name__ == "__main__":
    print("Бот активен")
    bot.infinity_polling()
