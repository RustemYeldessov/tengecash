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
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

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
/catadd - создать новую категорию
/catedit - редактировать список категорий
/catdelete - удалить категорию и ее содержимое

/list - список последних 10-ти расходов
/total - сумма расходов за текущий месяц

/site - перейти на веб-сайт Tenge Cash
"""

class LoginStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()


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
            "Пожалуйста, введи команду для привязки: /login"
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
async def handle_login(message: Message, state: FSMContext):
    await message.answer("Введи логин:")
    await state.set_state(LoginStates.waiting_for_username)

@dp.message(LoginStates.waiting_for_username)
async def process_username(message: Message, state: FSMContext):
    await state.update_data(chosen_username=message.text)
    await message.answer("Введи пароль:")
    await state.set_state(LoginStates.waiting_for_password)

@dp.message(LoginStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    user_data = await state.get_data()
    username = user_data['chosen_username']
    password = message.text

    await message.delete()
    result = await bind_user_with_password(message.from_user.id, username, password)
    await message.answer(result)
    await state.clear()


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


@sync_to_async
def get_categoies_db(user):
    return list(Category.objects.filter(user=user))

@dp.message(Command("catlist"))
async def handle_catlist(message: Message):
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        await message.answer("Сначала нужно авторизоваться, используй /login")
        return

    categories = await get_categoies_db(user)
    if not categories:
        await message.answer(
            "В базе пока нет категорий."
            "Добавь их в браузерной версии /site или при помощи команды /catadd."
        )
        return

    response_text = '<b>📁 Твои категории расходов:</b>\n\n'
    for index, cat in enumerate(categories, start=1):
        # section_name = cat.section.name if cat.section else "Без раздела"
        response_text += f"{index}. {cat.name}\n"
    await message.answer(response_text, parse_mode="HTML")


class CategoryEditStates(StatesGroup):
    selecting_category = State()
    remaining_category = State()
    waiting_for_new_cat_name = State()

@dp.message(Command("catedit"))
async def handle_catedit(message: Message):
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        await message.answer("Сначала нужно авторизоваться, используй /login")
        return

    categories = await get_categoies_db(user)
    if not categories:
        await message.answer(
            "В базе пока нет категорий."
            "Добавь их в браузерной версии /site или при помощи команды /catadd."
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✏️ {cat.name}", callback_data=f"edit_{cat.id}")]
        for cat in categories
    ])
    await message.answer("Выбери категорию для редактирования:", reply_markup=keyboard)

@sync_to_async
def update_category_name(cat_id, new_name):
    Category.objects.filter(id=cat_id).update(name=new_name)

@dp.callback_query(F.data.startswith("edit_"))
async def process_edit_category(callback: CallbackQuery, state: FSMContext):
    cat_id = callback.data.split("_")[1]
    await state.update_data(editing_cat_id=cat_id)

    await callback.message.edit_text("Введи новое название для этой категории:")
    await state.set_state(CategoryEditStates.remaining_category)
    await callback.answer()

@sync_to_async
def category_exists(user, name):
    return Category.objects.filter(user=user, name__iexact=name).exists()

@dp.message(CategoryEditStates.remaining_category)
async def process_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("editing_cat_id")
    new_name = message.text.strip()

    user = await get_user_by_tg_id(message.from_user.id)

    if await category_exists(user, new_name):
        await message.answer(
            f"❌ Категория с именем <b>{new_name}</b> уже существует!\n"
            "Введи другое название:",
            parse_mode="HTML"
        )
        return

    await update_category_name(cat_id, new_name)

    await message.answer(
        f"✅ Категория успешно переименована в: <b>{new_name}</b>",
            parse_mode="HTML"
    )
    await state.clear()


@sync_to_async
def create_category(user, name):
    return Category.objects.create(user=user, name=name)

@dp.message(Command("catadd"))
async def handle_category_create(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        await message.answer("Сначала нужно авторизоваться, используй /login")
        return

    await message.answer("Введи название новой категории:")
    await state.set_state(CategoryEditStates.waiting_for_new_cat_name)

@dp.message(CategoryEditStates.waiting_for_new_cat_name)
async def process_add_category(message: Message, state: FSMContext):
    new_cat_name = message.text.strip()
    user = await get_user_by_tg_id(message.from_user.id)

    if await category_exists(user, new_cat_name):
        await message.answer(
            f"❌ Категория с именем <b>{new_cat_name}</b> уже существует!\n"
            "Введи другое название:",
            parse_mode="HTML"
        )
        return

    await create_category(user, new_cat_name)
    await message.answer(
        f"✅ Категория <b>{new_cat_name}</b> успешно создана!",
            parse_mode="HTML"
    )
    await state.clear()


@sync_to_async
def category_delete(user, cat_id):
    return Category.objects.filter(id=cat_id, user=user).delete()

@dp.message(Command("catdelete"))
async def handle_category_delete(message: Message):
    tg_id = message.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        await message.answer("Сначала нужно авторизоваться, используй /login")
        return

    categories = await get_categoies_db(user)
    if not categories:
        await message.answer(
            "В базе пока нет категорий."
            "Добавь их в браузерной версии /site или при помощи команды /catadd."
        )
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {cat.name}", callback_data=f"delete_{cat.id}")]
        for cat in categories
    ])
    await message.answer("Выбери категорию для удаления:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("delete_"))
async def process_delete_category(callback: CallbackQuery):
    cat_id = callback.data.split("_")[1]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить ✅", callback_data=f"confirm_delete_{cat_id}"),
            InlineKeyboardButton(text="Отмена ❌", callback_data=f"cancel_delete")
        ]
    ])

    await callback.message.edit_text(
        "⚠️ <b>Внимание!</b>\n"
        "При удалении категории удалятся и все расходы, связанные с ней.\n"
        "Ты уверен?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete(callback: CallbackQuery):
    cat_id = callback.data.split("_")[2]
    tg_id = callback.from_user.id
    user = await get_user_by_tg_id(tg_id)

    await category_delete(user, cat_id)

    await callback.message.edit_text("✅ Категория и все её расходы успешно удалены.")
    await callback.answer()

@dp.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("Действие отменено. Данные в сохранности! 😌")
    await callback.answer()


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