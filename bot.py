# bot.py

import logging
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import BOT_TOKEN, SPREADSHEET_ID, SHEET_NAME

# ================= ЛОГИ =====================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Стадії діалогу
TYPE_BODY, DIRECTIONS, TRUCKS, CONTACT = range(4)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# =============== GOOGLE SHEETS ===============

def get_sheets_service():
    """Створюємо клієнт для Google Sheets."""
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def save_to_sheet(data: dict):
    """
    Записуємо рядок у таблицю ASTRIXT telegram BOT.

    Структура колонок:
    A: Дата додавання
    B: CARRIER_ID
    C: Тип кузова
    D: Напрямки роботи
    E: Кількість авто
    F: Контактна особа
    G: Телефон
    H: Email
    I: Примітки
    J: Джерело (Bot/Email/Viber/Manual)
    """
    service = get_sheets_service()
    sheet = service.spreadsheets()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    values = [[
        now_str,                        # A: дата додавання
        data.get("carrier_id", ""),     # B: CARRIER_ID (з параметра /start)
        data.get("body_type", ""),      # C: тип кузова
        data.get("directions", ""),     # D: напрямки роботи
        data.get("trucks", ""),         # E: кількість авто
        data.get("contact_person", ""), # F: контактна особа / текст
        data.get("phone", ""),          # G: телефон (якщо окремо будемо питати)
        data.get("email", ""),          # H: email
        data.get("notes", ""),          # I: примітки
        "Bot",                          # J: джерело
    ]]

    body = {"values": values}

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:J",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()

    logger.info("Рядок успішно записано в Google Таблицю.")


# =============== ХЕНДЛЕРЫ БОТА ===============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Точка входу: /start або посилання з параметром:
    https://t.me/astrixTbot?start=<CARRIER_ID>

    Тут читаємо CARRIER_ID з context.args і кладемо в user_data.
    """

    message = update.message or update.effective_message
    if not message:
        return ConversationHandler.END

    # Читаем параметр после /start
    args = context.args
    carrier_id = args[0] if args else ""
    context.user_data["carrier_id"] = carrier_id

    logger.info(
        f"/start від user_id={message.from_user.id}, "
        f"username={message.from_user.username}, CARRIER_ID={carrier_id}"
    )

    keyboard = [
        ["Тент", "Рефрижератор"],
        ["Зерновоз", "Контейнеровоз"],
        ["Платформа", "Цистерна"],
    ]

    await message.reply_text(
        "Вітаємо в ASTRIXT 🚛\n\n"
        "Оберіть, будь ласка, тип напівпричепа, з яким ви працюєте:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return TYPE_BODY


async def type_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 1 — тип кузова."""
    message = update.message
    if not message:
        return TYPE_BODY

    body_type = message.text
    context.user_data["body_type"] = body_type

    keyboard = [
        ["Україна → Польща", "Польща → Україна"],
        ["Україна → Німеччина", "Німеччина → Україна"],
        ["Країни Балтії", "Італія / Франція / Іспанія"],
        ["Інші напрямки"],
    ]

    await message.reply_text(
        "На яких напрямках працюєте постійно?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return DIRECTIONS


async def directions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 2 — напрямки роботи."""
    message = update.message
    if not message:
        return DIRECTIONS

    directions_value = message.text
    context.user_data["directions"] = directions_value

    keyboard = [
        ["1 авто", "2–3"],
        ["4–10", "Більше 10"],
    ]

    await message.reply_text(
        "Скільки авто ви можете виділити під нашу співпрацю?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return TRUCKS


async def trucks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 3 — кількість авто."""
    message = update.message
    if not message:
        return TRUCKS

    trucks_value = message.text
    context.user_data["trucks"] = trucks_value

    await message.reply_text(
        "Залиште, будь ласка, контакт для звʼязку "
        "(імʼя, телефон, за бажанням — email):",
        reply_markup=ReplyKeyboardRemove(),
    )

    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крок 4 — контактні дані, фінальний запис у таблицю."""
    message = update.message
    if not message:
        return ConversationHandler.END

    contact_text = message.text

    # Поки що все зберігаємо в одне поле "Контактна особа"
    context.user_data["contact_person"] = contact_text
    context.user_data["phone"] = ""
    context.user_data["email"] = ""
    context.user_data["notes"] = ""

    logger.info(f"Фінальні дані user_data: {context.user_data}")

    # Записуємо в Google Таблицю
    save_to_sheet(context.user_data)

    await message.reply_text(
        "Дякуємо! Дані збережено ✅\n\n"
        "Ми будемо надсилати вам підходящі вантажі через ASTRIXT."
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасування діалогу."""
    message = update.message or update.effective_message
    if message:
        await message.reply_text(
            "Опитування перервано. Якщо захочете продовжити — напишіть /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
    context.user_data.clear()
    return ConversationHandler.END


# =============== MAIN ========================

def main():
    logger.info("Запуск бота ASTRIXT carrier bot...")

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE_BODY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, type_body)
            ],
            DIRECTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, directions)
            ],
            TRUCKS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trucks)
            ],
            CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
