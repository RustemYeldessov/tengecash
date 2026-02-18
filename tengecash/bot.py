import asyncio
import os
from decimal import Decimal

import django
from django.contrib.auth import authenticate
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


HELP_COMMAND = """
/info - инструкция по внесению трат
/start - начать работу с ботом
/login - регистрация в Tenge Cash
/logout - выход из бота

/catlist - список категорий
/catedit - редактировать список категорий

/list - список последних 10-ти расходов
/total - сумма расходов за текущий месяц

/site - перейти на веб-сайт Tenge Cash
"""

@sync_to_async
def get_user_by_tg_id(tg_id):
    return User.objects.filter(telegram_id=tg_id).first()

@dp.message(Command("start"))
async def handle_start(message: Message):
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)
    if user:
        await message.answer(f'С возвращением, {user.username}!')
    else:
        await message.answer(
            "Упс... Ты не авторизован.\n"
            "Пожалуйста, введи команду для привязки:\n"
            "/login логин пароль"
        )


@sync_to_async
def bind_user_with_password(tg_id, django_username, password):
    user = authenticate(username=django_username, password=password)
    if user is not None:
        user.telegram_id = tg_id
        user.save()
        return f"Получилось! Ты вошел как пользователь {django_username}!"
    return "Ошибка: Пользователь с таким именем не найден в базе данных"


@dp.message(Command("login"))
async def handle_login(message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Введи: /login логин пароль")
        return
    result = await bind_user_with_password(message.from_user.id, args[1], args[2])
    await message.answer(result)
    await message.delete()


@sync_to_async
def logout_user_db(tg_id):
    user = User.objects.filter(telegram_id=tg_id).first()
    if user:
        user.telegram_id = None
        user.save()
        return True
    return False

@dp.message(Command("logout"))
async def handle_logout(message: Message):
    success = await logout_user_db(message.from_user.id)
    if success:
        await message.answer('Выход выполнен успешно. Для повторного входа выполни команду /login')
    else:
        await message.answer('Ты не был авторизован')


@dp.message(Command("help"))
async def handle_help(message: Message):
    await message.answer(text=HELP_COMMAND)


@dp.message(Command("info"))
async def handle_info(message: Message):
    await message.answer('Ввели трату в формате "Трата Сумма", например "Кофе 1000"')


async def main():
    print('Бот запущен...')
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())