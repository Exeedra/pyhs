from aiogram import F, types, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import orm_add_to_cart, orm_add_user
from filters.chat_types import ChatTypeFilter
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_callback_btns, get_payment_buttons, get_delivery_buttons

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(["private"]))


class OrderState(StatesGroup):
    phone = State()
    delivery_method = State()
    waiting_for_location = State()
    payment_method = State()


@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, session: AsyncSession):
    media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
    await message.answer_photo(media.media, caption=media.caption, reply_markup=reply_markup)


@user_private_router.callback_query(MenuCallBack.filter(F.menu_name == "order"))
async def order_cmd(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Пожалуйста, введите ваш номер телефона в формате +7XXXXXXXXXX:")
    await state.set_state(OrderState.phone)


@user_private_router.message(OrderState.phone, F.text)
async def get_phone(message: types.Message, state: FSMContext, session: AsyncSession):
    phone = message.text
    user = message.from_user
    await orm_add_user(session, user_id=user.id, first_name=user.first_name, last_name=user.last_name, phone=phone)
    await message.answer("Выберите способ доставки:", reply_markup=get_delivery_buttons())
    await state.set_state(OrderState.delivery_method)


@user_private_router.callback_query(OrderState.delivery_method, F.data == 'pickup')
async def pickup(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Вот ссылка на локацию: (https://yandex.ru/maps/?whatshere%5Bzoom%5D=16&whatshere%5Bpoint%5D=69.509435,41.309703)")
    await callback.message.answer("Выберите способ оплаты:", reply_markup=get_payment_buttons())
    await state.set_state(OrderState.payment_method)
    await callback.answer()


@user_private_router.callback_query(OrderState.delivery_method, F.data == 'courier')
async def courier(callback: types.CallbackQuery, state: FSMContext):
    test_kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Отправить локацию 🗺️", request_location=True),
            ],
        ],
        resize_keyboard=True,
    )
    await callback.message.answer(
        "Пожалуйста, отправьте вашу локацию.",
        reply_markup=test_kb
    )
    await state.set_state(OrderState.waiting_for_location)
    await callback.answer()


@user_private_router.message(OrderState.waiting_for_location, F.location)
async def get_location(message: types.Message, state: FSMContext):
    location = message.location
    latitude = location.latitude
    longitude = location.longitude

    # Здесь вы можете сохранить локацию пользователя (latitude и longitude) в базе данных, 
    # использовать ее для расчета стоимости доставки или отобразить на карте.

    await message.answer(f"Ваша локация: {latitude}, {longitude}", reply_markup=ReplyKeyboardRemove()) 
    await message.answer("Выберите способ оплаты:", reply_markup=get_payment_buttons()) # Отправляем кнопки оплаты в новом сообщении
    await state.set_state(OrderState.payment_method)


@user_private_router.callback_query(OrderState.payment_method, F.data.in_({'cash', 'prepayment'}))
async def payment_method(callback: types.CallbackQuery, state: FSMContext):
    payment_method = callback.data
    await callback.message.answer(f"Вы выбрали способ оплаты: {payment_method}. Заказ оформлен!")
    await state.clear()
    await callback.answer()


async def add_to_cart(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    user = callback.from_user
    await orm_add_user(
        session,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=None,
    )
    await orm_add_to_cart(session, user_id=user.id, product_id=callback_data.product_id)
    await callback.answer("Товар добавлен в корзину.")


@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    if callback_data.menu_name == "add_to_cart":
        await add_to_cart(callback, callback_data, session)
        return

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        category=callback_data.category,
        page=callback_data.page,
        product_id=callback_data.product_id,
        user_id=callback.from_user.id,
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()