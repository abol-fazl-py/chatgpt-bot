import os
import io
import base64
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# مدل رایگان از OpenRouter؛ می‌تونی بعداً عوضش کنی
# لیست مدل‌های رایگان به ترتیب اولویت؛ اگه یکی کار نکرد، بعدی امتحان می‌شه
# نکته: مدل‌های رایگان OpenRouter گاهی منقضی/جایگزین می‌شن. اگه همه خطا دادن،
# باید از سایت openrouter.ai/chat یه مدل رایگان جدید پیدا کنی و اینجا اضافه‌ش کنی.
MODELS = [
    "inclusionai/ling-3.0-flash-vl:free",
    "inclusionai/ling-3.0-flash-sante:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "openai/gpt-oss-20b:free",
    "deepseek/deepseek-chat-v3.1:free",
    "qwen/qwen3-coder:free",
    "qwen/qwen3-4b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "google/gemma-3-27b-it:free",
]

# مدل‌هایی که قابلیت دیدن و توضیح عکس (Vision) رو دارن
VISION_MODELS = [
    "inclusionai/ling-3.0-flash-vl:free",
    "qwen/qwen2.5-vl-7b-instruct:free",
    "nvidia/nemotron-nano-12b-2-vl:free",
]

# حافظه‌ی مکالمه برای هر کاربر (به‌صورت ساده، در حافظه‌ی برنامه)
user_histories = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! هر سوالی داری بپرس، جواب می‌دم. 🤖\n"
        "می‌تونی عکس هم برام بفرستی تا توضیحش بدم.\n"
        "برای پاک کردن حافظه‌ی مکالمه، دستور /reset رو بزن."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد. ✅")


def call_ai(messages, models_list):
    """پیام‌ها رو به مدل‌های لیست‌شده می‌ده تا یکی جواب بده؛ جواب یا خطای آخر رو برمی‌گردونه."""
    last_error = None
    for model in models_list:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], None
        except Exception as e:
            last_error = e
            continue
    return None, last_error


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_histories:
        user_histories[user_id] = []

    # اضافه کردن پیام کاربر به تاریخچه
    user_histories[user_id].append({"role": "user", "content": user_text})

    # فقط ۱۰ پیام آخر رو نگه می‌داریم تا زیاد سنگین نشه
    history = user_histories[user_id][-10:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    reply, error = call_ai(history, MODELS)

    if reply:
        user_histories[user_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(f"خطا در دریافت پاسخ (همه‌ی مدل‌ها امتحان شد):\n{error}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # بزرگ‌ترین سایز عکس رو بردار (بهترین کیفیت)
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    # دانلود عکس به‌صورت بایت و تبدیل به base64
    photo_bytes = await file.download_as_bytearray()
    b64_image = base64.b64encode(photo_bytes).decode("utf-8")

    # اگه کاربر زیر عکس متنی نوشته باشه (caption)، همون رو به‌عنوان سوال استفاده می‌کنیم
    user_caption = update.message.caption or "این عکس رو توضیح بده."

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_caption},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                },
            ],
        }
    ]

    reply, error = call_ai(messages, VISION_MODELS)

    if reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(f"خطا در پردازش عکس (همه‌ی مدل‌ها امتحان شد):\n{error}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
