import os
from django.utils import timezone
from decimal import Decimal

import django
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tengecash.settings')
django.setup()

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from asgiref.sync import sync_to_async

from tengecash.users.models import User
from tengecash.categories.models import Category
from tengecash.sections.models import Section
from tengecash.expenses.models import Expense


@sync_to_async
def link_user(tg_id, username):
    try:
        user = User.objects.get(username='yeldessovrus')
        if not user.telegram_id:
            user.telegram_id = tg_id
            user.save()
            return f'Приятно познакомиться, {user.username}! Твой Telegram привязан.'
        return f'С возвращением, {user.username}!'
    except User.DoesNotExist:
        return "Пользователь не найден."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    message = await link_user(tg_id, update.effective_user.username)
    await update.message.reply_text(message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    tg_id = update.effective_user.id

    try:
        parts = text.split()
        amount = Decimal(parts[0].replace(',', '.'))
        description = " ".join(parts[1:]) if len(parts) > 1 else ""

        context.user_data['temp_amount'] = amount
        context.user_data['temp_description'] = description

        categories = await get_categories()

        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat.name, callback_data=f"cat_{cat.id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Сумма: {amount}₸. Выбери категорию:", reply_markup=reply_markup)

    except Exception:
        await update.message.reply_text("Введи сумму (например, 1000)")

@sync_to_async
def get_categories():
    return list(Category.objects.all())

async def category_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.replace("cat_", ""))
    tg_id = update.effective_user.id

    amount = context.user_data.get('temp_amount')
    description = context.user_data.get('temp_description')

    result = await finalize_expense(tg_id, amount, cat_id, description)
    await query.edit_message_text(text=result)

@sync_to_async
def finalize_expense(tg_id, amount, cat_id, description):
    try:
        user = User.objects.get(telegram_id=tg_id)
        category = Category.objects.get(id=cat_id)
        # section = category.section if category.section else Section.objects.first()
        section = Section.objects.first()

        Expense.objects.create(
            user=user,
            amount=amount,
            category=category,
            section=section,
            description=description or category.name,
            date=timezone.now().date()
        )
        return f"✅ Записано: {amount} ₸ — {category.name}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


if __name__ == '__main__':
    # Читаем токен из переменных окружения
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.add_handler(CallbackQueryHandler(category_button_click))

    print("Бот запущен...")
    application.run_polling()