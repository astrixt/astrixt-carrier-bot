import logging
from datetime import datetime
import os
import json

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
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

from config import BOT_TOKEN, SPREADSHEET_ID, SHEET_NAME, CHANNEL_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Стадії діалогу
TYPE_BODY, DIRECTIONS, TRUCKS, CONTACT = range(4)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_service():
    """
    Створюємо клієнт Google Sheets, використовуючи JSON сервісного акаунта
    з змінної оточення GOOGLE_CREDENTIALS (Railway → Variables).
    """
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise RuntimeError(
            "Не знайдено змінну оточення GOOGLE_CREDENTIALS. "
            "Додай її в Railway у вкладці Variables."
        )

    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def save_to_sheet(data: dict):
    service = get_sheets_service()
    sheet = service.spreadsheets()

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    values = [[
        now,                            # A - Дата додавання
        "",                             # B - Назва компанії (поки пусто)
        data.get("body_type", ""),      # C - Тип кузова
        data.get("directions", ""),     # D - Напрямки роботи (регіони)
        data.get("trucks", ""),         # E - Кількість авто
        data.get("contact", ""),        # F - Контактна особа + телефон
        "",                             # G - Телефон (окремо, якщо захочеш потім)
        "",                             # H - Email
        "",                             # I - Примітки
        "Bot",                          # J - Джерело
    ]]

    body = {"values": values}

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:J",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


# === Хендлери ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    logger.info("Start from %s", user.id if user else "unknown")

    keyboard = [
        ["Тентований", "Рефрижератор"],
        ["Зерновоз", "Контейнеровоз"],
        ["Платформа", "Цистерна"],
    ]

    text = (
        "Вітаємо в ASTRIXT!\n\n"
        "Привіт! Це Astrix – ваш партнер, який дійсно розуміє ваші потреби. "
        "З нами ваш транспорт завжди на правильному шляху.\n\n"
        "1/4. Оберіть тип напівпричепа, з яким ви працюєте:"
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
    return TYPE_BODY


async def body_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Питання 2: регіони / напрямки роботи."""
    body_type_text = update.message.text.strip()
    context.user_data["body_type"] = body_type_text

    keyboard = [
        ["Польща — Німеччина", "Країни Бенілюксу"],
        ["Країни Балтії", "Італія"],
        ["Франція", "Іспанія"],
        ["Балканські країни", "Країни Азії"],
    ]

    text = (
        "2/4. Які напрямки або групи країн ваші вантажівки відвідують "
        "на постійній основі?\n\n"
        "Оберіть основний регіон роботи."
    )

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return DIRECTIONS


async def directions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Зберігаємо обраний регіон роботи та переходимо до кількості авто."""
    directions_text = update.message.text.strip()
    context.user_data["directions"] = directions_text

    keyboard = [["1", "2–3"], ["4–10", "10+"]]

    text = "3/4. Скільки у вас авто, які можуть працювати з нами?"

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return TRUCKS


async def trucks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trucks_text = update.message.text.strip()
    context.user_data["trucks"] = trucks_text

    text = (
        "4/4. Напишіть, будь ласка, ім’я та номер телефону для зв’язку.\n"
        "Можна в одному повідомленні, у будь-якому форматі."
    )

    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_text = update.message.text.strip()
    context.user_data["contact"] = contact_text

    try:
        save_to_sheet(context.user_data)
        logger.info("Saved carrier: %s", context.user_data)
        text = (
            "Дякуємо! Ваш профіль додано в базу перевізників ASTRIXT. ✅\n\n"
            "Натисніть кнопку нижче, щоб приєднатись до каналу з актуальними вантажами."
        )
    except Exception as e:
        logger.error("Error saving to sheet: %s", e)
        text = (
            "Сталася помилка при збереженні анкети. 😔\n"
            "Спробуйте, будь ласка, трохи пізніше або звʼяжіться з логістом напряму."
        )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("➡️ Вступити в канал ASTRIXT", url=CHANNEL_URL)]]
    )

    await update.message.reply_text(text, reply_markup=keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Анкету скасовано. Якщо захочете продовжити, надішліть /start.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, body_type)],
            DIRECTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, directions)],
            TRUCKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, trucks)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
