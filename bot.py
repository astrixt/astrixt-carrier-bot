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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Стадії діалогу
TYPE_BODY, DIRECTIONS, TRUCKS, CONTACT = range(4)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def save_to_sheet(data: dict):
    """
    Записуємо дані у Google Таблицю.
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
        now_str,
        data.get("carrier_id", ""),       # 👉 ВАЖНО: сюда пишем CARRIER_ID
        data.get("body_type", ""),
        data.get("directions", ""),
        data.get("trucks", ""),
        data.get("contact_person", ""),
        data.get("phone", ""),
        data.get("email", ""),
        data.get("notes", ""),
        "Bot",                            # джерело
    ]]

    body = {
        "values": values
    }

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:J",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start ?start=<CARRIER_ID>

    Тут зчитуємо CARRIER_ID з аргументів і кладемо його в context.user_data.
    Далі запускаємо опитування.
    """

    # 1. Читаем аргументы после /start
    args = context.args
    carrier_id = args[0] if args else ""

    # 2. Сохраняем в user_data
    context.user_data["carrier_id"] = carrier_id

    logger.info(f"Start from user {update.effective_user.id}, CARRIER_ID={carrier_id}")

    keyboard = [
        ["Тент", "Рефрижератор"],
        ["Зерновоз", "Контейнеровоз"],
        ["Платформа", "Цистерна"],
    ]

    await update.message.reply_text(
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
    body_type = update.message.text
    context.user_data["body_type"] = body_type

    keyboard = [
        ["Україна → Польща", "Польща → Україна"],
        ["Україна → Німеччина", "Німеччина → Україна"],
        ["Країни Балтії", "Італія / Франція / Іспанія"],
        ["Інші напрямки"],
    ]

    await update.message.reply_text(
        "На яких напрямках працюєте постійно?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return DIRECTIONS


async def directions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    directions_value = update.message.text
    context.user_data["directions"] = directions_value

    keyboard = [
        ["1 авто", "2–3"],
        ["4–10", "Більше 10"],
    ]

    await update.message.reply_text(
        "Скільки авто ви можете виділити під нашу співпрацю?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return TRUCKS


async def trucks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trucks_value = update.message.text
    context.user_data["trucks"] = trucks_value

    await update.message.reply_text(
        "Залиште, будь ласка, контакт для звʼязку "
        "(імʼя, телефон, за бажанням — email):",
        reply_markup=ReplyKeyboardRemove(),
    )

    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_text = update.message.text

    # Можно тут как угодно парсить, но пока кладём всё в контактну особу
    context.user_data["contact_person"] = contact_text
    context.user_data["phone"] = ""
    context.user_data["email"] = ""
    context.user_data["notes"] = ""

    # Сохраняем в таблицу
    save_to_sheet(context.user_data)

    await update.message.reply_text(
        "Дякуємо! Дані збережено ✅\n\n"
        "Ми будемо надсилати вам підходящі вантажі через ASTRIXT."
    )

    # очищаем user_data при желании
    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Опитування перервано. Якщо захочете продовжити — напишіть /start.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


def main():
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
