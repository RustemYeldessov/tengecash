import asyncio
import os
from decimal import Decimal

import django
from django.utils import timezone
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tengecash.settings')
django.setup()

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from tengecash.users.models import User
from tengecash.categories.models import Category
from tengecash.sections.models import Section
from tengecash.expenses.models import Expense

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer('Привет! Я - Tenge Cash Bot!')

async def main():
    print('Бот запущен...')
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())