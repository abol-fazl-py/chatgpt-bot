import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# مدل رایگان از OpenRouter؛ می‌تونی بعداً عوضش کنی
MODEL = "openai/gpt-oss-20b:free"

# حافظه‌ی مکالمه برای هر کاربر (به‌صورت ساده، در حافظه‌ی برنامه)
user_histories = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! هر سوالی داری بپرس، جواب می‌دم. 🤖\n"
        "برای پاک کردن حافظه‌ی مکالمه، دستور /reset رو بزن."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text("حافظه‌ی مکالمه پاک شد. ✅")


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

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": history,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"]

        # اضافه کردن جواب ربات به تاریخچه
        user_histories[user_id].append({"role": "assistant", "content": reply})

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"خطا در دریافت پاسخ:\n{e}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
