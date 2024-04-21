import logging
import requests
import asyncio
import random
import string
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.ext import *
from telegram import InlineKeyboardButton, InlineKeyboardMarkup,ReplyKeyboardMarkup, KeyboardButton


# Настройки базы данных
DATABASE_FILE = 'bot_database.db'
DATABASE_URL = f'sqlite:///{DATABASE_FILE}'
Base = declarative_base()
engine = create_engine(DATABASE_URL)


# Определение модели пользователя в БД
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    access_key = Column(String)
    is_admin = Column(Boolean, default=False)
    interval = Column(Integer, default=300)


# Определение модели приложения в БД
class App(Base):
    __tablename__ = 'apps'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    url = Column(String)
    launch_link = Column(String)
    availability = Column(Boolean, default=True)


# Проверяем существование файла базы данных и создаем соединение
try:
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    print("Подключение к базе данных установлено успешно.")
except Exception as e:
    print("Ошибка при подключении к базе данных:", e)

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Функция для получения списка команд в зависимости от статуса пользователя
def get_commands(user_is_admin: bool) -> str:
    """
       Возвращает список доступных команд в зависимости от статуса пользователя.

       Args:
           user_is_admin (bool): Флаг, указывающий, является ли пользователь администратором.

       Returns:
           str: Список доступных команд.
       """
    if user_is_admin:
        commands = "/add - Добавить приложение для мониторинга\n" \
                   "/remove - Удалить приложение из мониторинга\n" \
                   "/set_interval - Установить интервал проверки доступности приложений\n" \
                   "/generate_key - Сгенерировать ключ доступа для пользователя\n" \
                   "/broadcast - Отправить сообщение всем пользователям"
    else:
        commands = "/subscribe - Подписаться на уведомления о доступности приложений\n" \
                   "/status - Просмотр статуса текущих приложений под мониторингом\n" \
                   "/get_launch_links - Получить ссылку для запуска приложения"
    return commands

# Функция для обработки команды /start
async def start(update: Update, context: CallbackContext) -> None:
    """
       Обрабатывает команду /start.

       Отправляет пользователю список доступных команд в зависимости от его статуса.
    """
    user_id = update.message.chat_id
    user = session.query(User).filter_by(chat_id=user_id).first()

    if not user:
        await update.message.reply_text("Для начала работы с ботом необходимо авторизоваться.")
        return

    print(f"User is admin: {user.is_admin}")  # Добавим отладочный вывод
    commands = get_commands(user.is_admin)
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Список приложений"),
                KeyboardButton(text="Сформировать ссылку для запуска"),
                KeyboardButton(text="FAQ")
            ]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(f"Доступные команды:\n{commands}", reply_markup=main_keyboard)

    # Отправляем действие "действующий" для закрепления клавиатуры на экране пользователя
    await context.bot.send_chat_action(chat_id=user_id, action="typing")

async def subscribe(update, context):
    """
        Обрабатывает команду /subscribe.

        Подписывает пользователя на уведомления о доступности приложений.
    """
    print("Received update:", update)
    user_id = update.message.chat_id
    print("User ID:", user_id)

    if update.message and update.message.text:
        access_key = context.args[0] if context.args else None
        print("Access key:", access_key)

        if access_key:
            user = session.query(User).filter_by(chat_id=user_id, access_key=access_key).first()
            print("User from DB with access key:", user)

            if user:
                user.chat_id = user_id
                session.commit()
                print("User subscribed successfully.")
                await update.message.reply_text("Вы успешно подписались на уведомления.")
            else:
                print("Invalid access key.")
                await update.message.reply_text("Неверный ключ доступа.")
        else:
            print("Access key is not provided.")
            await update.message.reply_text("Для подписки на уведомления необходимо указать ключ доступа.")
    else:
        print("Received empty or non-text message")


# Функция для обработки команды /add
async def add(update: Update, context: CallbackContext) -> None:
    """
       Обрабатывает команду /add.

       Добавляет новое приложение для мониторинга.

       Args:
           update (Update): Объект, содержащий информацию о входящем сообщении.
           context (CallbackContext): Контекст обработки команды.

    """
    user_id = update.message.chat_id
    user = session.query(User).filter_by(chat_id=user_id).first()

    if user and user.is_admin:
        if len(context.args) != 3:
            await update.message.reply_text(
                "Неверное количество аргументов. Используйте: /add [URL приложения] [Название] [Ссылка запуска]")
            return

        url, name, launch_link = context.args
        # Проверяем, существует ли уже приложение с таким названием
        existing_app = session.query(App).filter_by(name=name).first()
        if existing_app:
            await update.message.reply_text("Приложение с таким названием уже существует.")
            return

        # Добавляем новое приложение в базу данных
        new_app = App(name=name, url=url, launch_link=launch_link)
        session.add(new_app)
        session.commit()
        await update.message.reply_text("Приложение успешно добавлено.")
    else:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")


# Функция для обработки команды /remove
async def remove(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /remove.

        Удаляет приложение из мониторинга.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    user_id = update.message.chat_id
    user = session.query(User).filter_by(chat_id=user_id).first()

    if user and user.is_admin:
        if len(context.args) != 1:
            await update.message.reply_text("Неверное количество аргументов. Используйте: /remove [Название]")
            return

        app_name = context.args[0]
        # Проверяем, существует ли приложение с таким названием
        app = session.query(App).filter_by(name=app_name).first()
        if app:
            # Удаляем найденное приложение из базы данных
            session.delete(app)
            session.commit()
            await update.message.reply_text("Приложение успешно удалено.")
        else:
            await update.message.reply_text("Приложение не найдено.")
    else:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")


# Функция для обработки команды /set_interval
async def set_interval(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /set_interval.

        Устанавливает интервал проверки доступности приложений.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    user_id = update.message.chat_id
    user = session.query(User).filter_by(chat_id=user_id).first()

    if user and user.is_admin:
        if len(context.args) != 1:
            await update.message.reply_text(
                "Неверное количество аргументов. Используйте: /set_interval [интервал в секундах]")
            return

        try:
            interval = int(context.args[0])
            if interval <= 0:
                await update.message.reply_text("Интервал должен быть положительным числом.")
                return
            user.interval = interval
            session.commit()
            await update.message.reply_text("Интервал успешно установлен.")
        except ValueError:
            await update.message.reply_text("Неверный формат интервала.")
    else:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")


# Функция для обработки команды /generate_key
async def generate_key(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /generate_key.

        Генерирует ключ доступа для пользователя.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    print("Received /generate_key command")  # Добавляем принт для отслеживания вызова команды

    user_id = update.effective_chat.id

    user = session.query(User).filter_by(chat_id=user_id).first()

    if user and user.is_admin:
        if len(context.args) != 1:
            context.bot.send_message(chat_id=user_id,
                                     text="Неверное количество аргументов. Используйте: /generatekey [ключ]")
            return

        access_key = context.args[0]

        print(f"Received access key: {access_key}")  # Добавляем принт для отслеживания полученного ключа доступа

        # Генерируем случайный ключ доступа и сохраняем его в базу данных
        new_key = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        user.access_key = new_key
        session.commit()

        print(f"Generated new access key: {new_key}")  # Добавляем принт для отслеживания сгенерированного ключа доступа

        # Отправляем сообщение с сгенерированным ключом доступа в чат бота
        await context.bot.send_message(chat_id=user_id, text=f"Ключ доступа успешно сгенерирован: {new_key}")
    else:
        await context.bot.send_message(chat_id=user_id, text="У вас нет прав на выполнение этой команды.")


# Функция для обработки команды /broadcast
async def broadcast(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /broadcast.

        Отправляет сообщение всем пользователям.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    user_id = update.message.chat_id
    user = session.query(User).filter_by(chat_id=user_id).first()

    if user and user.is_admin:
        if len(context.args) < 1:
            await update.message.reply_text("Неверное количество аргументов. Используйте: /broadcast [сообщение]")
            return

        message = ' '.join(context.args)

        # Получаем всех пользователей из базы данных
        users = session.query(User).all()
        for u in users:
            # Отправляем сообщение каждому пользователю
            await context.bot.send_message(chat_id=u.chat_id, text=message)

        await update.message.reply_text("Уведомление успешно отправлено всем пользователям.")
    else:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")

# Функция для обработки команды /status
async def status(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /status.

        Отображает статус текущих приложений под мониторингом.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    # Формирование клавиатуры с кнопками для выбора приложения
    keyboard = []
    apps = session.query(App).all()
    for app in apps:
        keyboard.append([InlineKeyboardButton(app.name, callback_data=str(app.id))])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text('Пожалуйста, выберите приложение для просмотра его статуса:',
                                    reply_markup=reply_markup)


async def get_launch_links(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает команду /get_launch_links.

        Отправляет пользователю список приложений с ссылками для их запуска.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    # Получаем список всех приложений из базы данных
    apps = session.query(App).all()

    # Проверяем, есть ли приложения в базе данных
    if not apps:
        await update.message.reply_text("Нет доступных приложений для выбора.")
        return

    # Формируем список кнопок для каждого приложения
    keyboard = [[InlineKeyboardButton(app.name, callback_data=str(app.id))] for app in apps]

    # Создаем разметку для клавиатуры
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с кнопками выбора приложения
    await update.message.reply_text('Пожалуйста, выберите приложение:', reply_markup=reply_markup)

async def select_app(update: Update, context: CallbackContext) -> None:
    """
        Обрабатывает выбор пользователя приложения для получения ссылки на его запуск.

        Args:
            update (Update): Объект, содержащий информацию о входящем сообщении.
            context (CallbackContext): Контекст обработки команды.

    """
    query = update.callback_query
    app_id = int(query.data)

    # Получаем информацию о выбранном приложении из базы данных
    app = session.query(App).filter_by(id=app_id).first()

    # Отправляем сообщение с информацией о выбранном приложении
    await query.message.reply_text(f"Вы выбрали приложение: {app.name}. Ссылка для запуска: {app.launch_link}")

async def check_availability():
    """
        Проверяет доступность приложений по их URL.

    """
    while True:
        apps = session.query(App).all()
        for app in apps:
            try:
                response = requests.get(app.url)
                if response.status_code != 200:
                    app.availability = False
                    session.commit()
                    await notify_users(app)  # Ожидаем уведомления
            except Exception as e:
                logging.error(f"Ошибка при проверке доступности для {app.name}: {e}")
        await asyncio.sleep(300)  # Используем asyncio.sleep для неблокирующего сна


async def notify_users(app):
    """
        Уведомляет пользователей о недоступности приложения.

        Args:
            app: Объект приложения, которое стало недоступным.

    """
    users = session.query(User).all()
    for user in users:
        await updater.bot.send_message(chat_id=user.chat_id, text=f"Приложение {app.name} недоступно!")


if __name__ == '__main__':
    application = Application.builder().token("YOUR TOKEN").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("set_interval", set_interval))
    application.add_handler(CommandHandler("generate_key", generate_key))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("check_availability", check_availability))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("get_launch_links", get_launch_links))
    application.add_handler(CallbackQueryHandler(select_app))
    application.run_polling(1.0)
