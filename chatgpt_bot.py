import os
import base64
import logging
import requests
from ddgs import DDGS
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# لیست مدل‌های رایگان به ترتیب اولویت؛ اگه یکی کار نکرد، بعدی امتحان می‌شه
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
        "برای پیدا کردن اسم یه آهنگ: /search <متن یا توضیح آهنگ>\n"
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
                json={"model": model, "messages": messages},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], None
        except Exception as e:
            last_error = e
            continue
    return None, last_error


def web_search(query: str, max_results: int = 5):
    """جستجوی وب رایگان با DuckDuckGo؛ لیستی از نتایج برمی‌گردونه."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results, None
    except Exception as e:
        return [], e


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)

    if not query:
        await update.message.reply_text(
            "بعد از /search بنویس دنبال چی می‌گردی.\n"
            "مثال: /search اسم آهنگی که این تیکه از متنشه: sen ağlama"
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    results, error = web_search(query)

    if error or not results:
        await update.message.reply_text("چیزی توی جستجوی وب پیدا نشد، دوباره امتحان کن.")
        return

    search_context = "\n\n".join(
        f"عنوان: {r.get('title')}\nخلاصه: {r.get('body')}\nلینک: {r.get('href')}"
        for r in results
    )

    prompt = (
        f"کاربر دنبال این چیز می‌گرده: {query}\n\n"
        f"این نتایج جستجوی وب رو دارم:\n{search_context}\n\n"
        "بر اساس این نتایج، جواب دقیق و کوتاهی به کاربر بده. "
        "اگه سوال درباره‌ی یه آهنگ بود، فقط اسم آهنگ، خواننده، و لینک رسمی شنیدنش (یوتیوب/اسپاتیفای) رو بده؛ "
        "هرگز متن کامل ترانه رو ننویس، فقط اسم و لینک."
    )

    reply, ai_error = call_ai([{"role": "user", "content": prompt}], MODELS)

    if reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(f"خطا در پردازش نتایج (همه‌ی مدل‌ها امتحان شد):\n{ai_error}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_histories:
        user_histories[user_id] = []

    user_histories[user_id].append({"role": "user", "content": user_text})
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

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    b64_image = base64.b64encode(photo_bytes).decode("utf-8")

    user_caption = update.message.caption or "این عکس رو توضیح بده."

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_caption},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
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
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
