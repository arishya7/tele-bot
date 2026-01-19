"""
Lightweight Telegram Bot for CoolRide
Points users to HuggingFace PWA for route calculation
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
APP_URL = os.environ.get("APP_URL", "https://thermal-optimizers-coolride-engine.hf.space")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
user_sessions = {}

FALLBACK_PLACES = {
    "nature": [
        {"name": "Botanic Gardens", "reason": "UNESCO site with lush greenery"},
        {"name": "East Coast Park", "reason": "Beachside cycling with sea breeze"},
        {"name": "Punggol Waterway", "reason": "Peaceful waterfront trail"},
    ],
    "food": [
        {"name": "Tiong Bahru", "reason": "Hip cafes in heritage shophouses"},
        {"name": "Joo Chiat", "reason": "Peranakan food and colorful streets"},
        {"name": "Kampong Glam", "reason": "Middle Eastern eats near Haji Lane"},
    ],
    "views": [
        {"name": "Marina Bay Sands", "reason": "Iconic skyline views"},
        {"name": "Gardens by the Bay", "reason": "Stunning Supertrees"},
        {"name": "Henderson Waves", "reason": "Highest pedestrian bridge"},
    ],
}

def geocode_location(place_name):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={place_name}, Singapore&format=json&limit=1"
        resp = requests.get(url, headers={"User-Agent": "CoolRide/1.0"}, timeout=5)
        data = resp.json()
        if data:
            return (float(data[0]['lat']), float(data[0]['lon']))
    except:
        pass
    return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = update.effective_user
    user_sessions[user_id] = {}
    username = user.username or user.first_name or f"user_{user_id}"

    keyboard = [
        [InlineKeyboardButton("🗺️ I know where I'm going", callback_data="mode_direct")],
        [InlineKeyboardButton("✨ Recommend me a place", callback_data="mode_recommend")]
    ]
    await update.message.reply_text(
        f"☀️ *Welcome to CoolRide, @{username}!*\n\n"
        f"I help you find cool, shaded cycling routes in Singapore.\n\n"
        f"What would you like to do?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *CoolRide Bot Help*\n\n"
        "/start - Plan a new route\n\n"
        "Just chat naturally! Tell me where you want to cycle.",
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    data = query.data

    if user_id not in user_sessions:
        user_sessions[user_id] = {}

    if data == "mode_direct":
        user_sessions[user_id] = {"mode": "direct"}
        await query.edit_message_text(
            "🗺️ Tell me where you want to cycle!\n\n"
            "Example: \"From Marina Bay to East Coast Park\""
        )

    elif data == "mode_recommend":
        keyboard = [
            [InlineKeyboardButton("🌿 Nature", callback_data="mood_nature"),
             InlineKeyboardButton("🍜 Food", callback_data="mood_food")],
            [InlineKeyboardButton("🌇 Views", callback_data="mood_views")]
        ]
        await query.edit_message_text("✨ *What are you in the mood for?*", 
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("mood_"):
        mood = data.replace("mood_", "")
        user_sessions[user_id]["mood"] = mood
        keyboard = [
            [InlineKeyboardButton("🚴 10-20 min", callback_data="dist_short")],
            [InlineKeyboardButton("🚴‍♂️ 20-40 min", callback_data="dist_medium")],
            [InlineKeyboardButton("🚴‍♀️ 40+ min", callback_data="dist_long")]
        ]
        await query.edit_message_text(f"*{mood.title()}* - nice!\n\n*How far?*",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("dist_"):
        mood = user_sessions.get(user_id, {}).get("mood", "nature")
        recs = FALLBACK_PLACES.get(mood, FALLBACK_PLACES["nature"])
        user_sessions[user_id]["recommendations"] = recs

        keyboard = [[InlineKeyboardButton(f"📍 {r['name']}", callback_data=f"place_{i}")] for i, r in enumerate(recs)]
        text = "🎯 *Top picks:*\n\n" + "\n".join([f"*{i+1}. {r['name']}*\n_{r['reason']}_\n" for i, r in enumerate(recs)])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith("place_"):
        idx = int(data.replace("place_", ""))
        recs = user_sessions.get(user_id, {}).get("recommendations", [])
        if idx < len(recs):
            user_sessions[user_id]["destination"] = recs[idx]["name"]
            user_sessions[user_id]["awaiting_start"] = True
            await query.edit_message_text(
                f"🎯 *Destination: {recs[idx]['name']}*\n\nWhere are you starting from?",
                parse_mode='Markdown'
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    session = user_sessions.get(user_id, {})

    if text.lower().strip() in ["hi", "hello", "hey", "start"]:
        await start_command(update, context)
        return

    if session.get("awaiting_start"):
        dest = session.get("destination", "")
        await update.message.reply_text("📍 Finding locations...")
        
        start_coords = geocode_location(text)
        end_coords = geocode_location(dest)

        if start_coords and end_coords:
            url = f"{APP_URL}?start={start_coords[0]},{start_coords[1]}&end={end_coords[0]},{end_coords[1]}&tg={user_id}"
            await update.message.reply_text(
                f"🗺️ *Route ready!*\n\n📍 {text} → {dest}\n\n👉 [Open map]({url})",
                parse_mode='Markdown'
            )
            user_sessions[user_id] = {}
        else:
            await update.message.reply_text("😕 Couldn't find location. Try again.")
        return

    # Simple route detection
    if "from" in text.lower() and "to" in text.lower():
        parts = text.lower().split("to")
        start = parts[0].replace("from", "").strip()
        end = parts[1].strip() if len(parts) > 1 else ""
        
        if start and end:
            await update.message.reply_text("📍 Finding locations...")
            start_coords = geocode_location(start)
            end_coords = geocode_location(end)
            
            if start_coords and end_coords:
                url = f"{APP_URL}?start={start_coords[0]},{start_coords[1]}&end={end_coords[0]},{end_coords[1]}&tg={user_id}"
                await update.message.reply_text(
                    f"🗺️ *Route ready!*\n\n📍 {start} → {end}\n\n👉 [Open map]({url})",
                    parse_mode='Markdown'
                )
                return

    await update.message.reply_text("Try /start to plan a route!")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return

    print(f"🚀 Starting CoolRide Bot...")
    print(f"   APP_URL: {APP_URL}")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
