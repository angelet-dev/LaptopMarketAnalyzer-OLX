import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from config_manager import ConfigManager
from LaptopBase import LaptopBase
from aiogram.exceptions import TelegramBadRequest
import logging


class SettingsStates(StatesGroup):
    remove = State()
    add = State()


dp = Dispatcher()


### Команда для стартового повідомлення ###


@dp.message(CommandStart())
async def cmd_start(message: types.Message, config: ConfigManager):
    """
    Обробляє команду /start. Виводить вітальне повідомлення та перелік доступних функцій.
    """
    try:
        logging.info(f"Користувач {message.from_user.id} запустив бота.")
        if "chat_id" not in config.data or config.data["chat_id"] == "":
            config.data["chat_id"] = message.chat.id
            config.save()
            logging.info("User ID saved to config.")

        text = (
            "Ви увійшли в бот для пошуку вигідних пропозицій на ноутбуки.\n\n"
            "Вам доступні наступні команди:\n\n"
            "/laptops - перегляд всіх вигідних пропозицій на обрані ноутбуки\n"
            "/settings - налаштування пошуку, зміни чорного списку та інші налаштування\n"
            "/scan - запуск сканування\n\n"
            "За стандартними налаштуваннями, бот проводить пошук за обраними моделями "
            "і присилає повідомлення про нові пропозиції.\n"
            "Для зміни налаштувань використовуйте /settings"
        )
        await message.answer(text)

    except Exception as e:
        logging.error(
            f"Помилка в cmd_start для користувача {message.from_user.id}: {e}"
        )


### Блок хендлерів для керування меню ноутбуків ###


def get_laptops_menu(
    index: int, laptops: LaptopBase
) -> tuple[str, str, types.InlineKeyboardMarkup]:
    """
    Генерує контентну картку ноутбука та інтерфейс керування.
    Формує текст із Deal Score, ціною та медіаною. Створює навігаційні кнопки.
    """
    try:
        is_new_prefix = "🔥 <b>НОВЕ!</b> " if laptops.is_new(index) else ""

        title = laptops["offer_title"][index]
        price = laptops["price"][index]
        score = laptops["deal_score"][index] * 100
        median = laptops["median"][index]
        link = laptops["link"][index]
        photo = laptops["image_link"][index]

        caption = (
            f"{is_new_prefix}<b>{title}</b>\n\n"
            f"💰 Ціна: <b>{price}</b> zł\n"
            f"📊 На <b>{score:.0f}%</b> менша за медіану ({median} zł)"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📝 Опис", callback_data=f"descr:{index}"),
            InlineKeyboardButton(text="🚫 Спам", callback_data=f"spam:{index}"),
            InlineKeyboardButton(text="🔗 OLX", url=link),
        )
        num_laptops = len(laptops)
        nav_buttons = []
        if index > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{index - 1}")
            )
        if index < num_laptops - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="Вперед ➡️", callback_data=f"next:{index + 1}")
            )

        if nav_buttons:
            builder.row(*nav_buttons)

        laptops.make_as_seen(index)

        return photo, caption, builder.as_markup()

    except Exception as e:
        logging.error(f"Критична помилка в get_laptops_menu на індексі {index}: {e}")
        return "", "Помилка формування картки.", InlineKeyboardBuilder().as_markup()


async def show_laptop_card(
    message: types.Message, index: int, laptops: LaptopBase
) -> None:
    """
    Відображає повідомлення з фото та кнопками або повідомлення про відсутність даних.
    """
    try:
        if laptops.df.empty:
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Перевірити нові пропозиції", callback_data="view_new_data"
                )
            )
            await message.answer(
                "😔 На жаль, зараз немає вигідних пропозицій.",
                reply_markup=builder.as_markup(),
            )
            return

        index = laptops.get_valid_index(index, -1)
        photo, caption, markup = get_laptops_menu(index, laptops)
        await message.answer_photo(
            photo=photo, caption=caption, reply_markup=markup, parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Помилка в show_laptop_card: {e}")
        await message.answer("Сталася помилка при відображенні картки ноутбука.")


@dp.message(Command("laptops"))
async def cmd_laptop(message: types.Message, laptops: LaptopBase) -> None:
    """
    Команда /laptops: оновлює дані з бази та показує першу картку.
    """
    try:
        laptops.update()
        direction = 1
        index = laptops.get_valid_index(0, direction)
        await show_laptop_card(message, index, laptops)
    except Exception as e:
        logging.error(f"Помилка в cmd_laptop: {e}")


@dp.callback_query(F.data.startswith("back"))
@dp.callback_query(F.data.startswith("next"))
async def press_navigation(callback: types.CallbackQuery, laptops: LaptopBase):
    """
    Обробляє кнопки "Назад" та "Вперед", оновлюючи поточне повідомлення (медіа та текст).
    """
    try:
        action, cur_index = callback.data.split(":")
        direction = 1 if action == "next" else -1
        index = laptops.get_valid_index(int(cur_index), direction)

        photo, caption, markup = get_laptops_menu(index, laptops)
        media = InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML")

        await callback.message.edit_media(media=media, reply_markup=markup)

    except TelegramBadRequest as e:
        if "Bad Request: wrong type of the web page content" in str(e):
            placeholder_url = 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRcCBHgbS23kyBw2r8Pquu19UtKZnrZmFUx1g&s'
            media = InputMediaPhoto(media=placeholder_url, caption=caption, parse_mode="HTML")
            await callback.message.edit_media(media=media, reply_markup=markup)
            logging.warning(f"Failed to load original photo ({e}). Media switched to placeholder.")
        else:
            await callback.answer()
            logging.error(f"Unexpected error while updating message media ({type(e).__name__}): {e}")

    except Exception as e:
        logging.error(f"Помилка навігації: {e}")
        await callback.answer("⚠️ Не вдалося змінити сторінку.")


@dp.callback_query(F.data.startswith("descr"))
async def press_description(callback: types.CallbackQuery, laptops: LaptopBase):
    """
    Замінює основний текст картки на повний опис товару з лімітом 1000 символів.
    """
    try:
        index = int(callback.data.split(":")[1])
        builder = InlineKeyboardBuilder().add(
            InlineKeyboardButton(text="⬆️ Повернутися", callback_data=f"next:{index}")
        )

        description = str(laptops["description"][index])
        if len(description) > 1024:
            description = "Опис\n" + description[4:1000] + "..."

        media = InputMediaPhoto(
            media=laptops["image_link"][index], caption=description, parse_mode="HTML"
        )
        await callback.message.edit_media(media=media, reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Помилка при відображенні опису: {e}")
        await callback.answer("⚠️ Не вдалося завантажити опис.")


@dp.callback_query(F.data.startswith("spam"))
async def press_spam(callback: types.CallbackQuery):
    """
    Викликає меню підтвердження для додавання оголошення в спам.
    """
    try:
        index = int(callback.data.split(":")[1])
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Так, в спам", callback_data=f"add_to_spam:{index}"
            )
        )
        builder.row(
            InlineKeyboardButton(text="❌ Ні, назад", callback_data=f"next:{index}")
        )

        await callback.message.delete()
        await callback.message.answer(
            text="❓ Ви точно хочете додати цей ноутбук в спам? Він більше не з'явиться у пошуку.",
            reply_markup=builder.as_markup(),
        )
    except Exception as e:
        logging.error(f"Помилка в press_spam: {e}")


@dp.callback_query(F.data.startswith("add_to_spam"))
async def add_to_spam(callback: types.CallbackQuery, laptops: LaptopBase) -> None:
    """
    Позначає товар як спам, зберігає зміни та повертає користувача до списку через паузу.
    """
    try:
        index = int(callback.data.split(":")[1])
        title = laptops["offer_title"][index]

        laptops.add_to_spam(index)
        laptops.save()

        if len(laptops) == 0:
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Оновити дані", callback_data="view_new_data"
                )
            )
            await callback.message.edit_text(
                "😞 Більше немає оголошень. Очікуйте нових знахідок.",
                reply_markup=builder.as_markup(),
            )
            return

        text = (
            f"🗑 Оголошення <b>{title}</b> в спамі!\n\n"
            f"<code>Через 3 секунди ви повернетесь до списку...</code>"
        )
        await callback.message.edit_text(text, parse_mode="HTML")

        await asyncio.sleep(3)

        new_index = laptops.get_valid_index(index, -1)

        photo, caption, markup = get_laptops_menu(new_index, laptops)
        await callback.message.answer_photo(
            photo=photo, caption=caption, reply_markup=markup, parse_mode="HTML"
        )
        await callback.message.delete()

    except Exception as e:
        logging.error(f"Помилка при додаванні в спам: {e}")
        await callback.answer("⚠️ Помилка при спробі видалити оголошення.")


@dp.callback_query(F.data == "view_new_data")
async def press_new_data(callback: types.CallbackQuery, laptops: LaptopBase):
    """
    Перезавантажує базу даних та намагається знову вивести список вигідних пропозицій.
    """
    try:
        laptops.update()

        if len(laptops) == 0:
            await callback.answer("Нічого нового не знайдено 😔", show_alert=True)
            return

        await callback.message.delete()
        await show_laptop_card(callback.message, 0, laptops)
    except Exception as e:
        logging.error(f"Помилка в press_new_data: {e}")


### Блок хендлерів для керування меню налаштувань моніторингу ###


def get_setting_ui(config: ConfigManager) -> tuple[str, types.InlineKeyboardMarkup]:
    """
    Генерує інтерфейс головного меню налаштувань.
    Відображає поточні ліміти, моделі та параметри фільтрації.
    """
    try:
        models = ", ".join(config.data.get("models", [])) or "Не обрано"
        black_list = ", ".join(config.data.get("blacklist", [])) or "Порожньо"
        min_d = config.data.get("min_deal_score", 0) * 100
        max_d = config.data.get("max_deal_score", 0) * 100
        interval = config.data.get("cheak_interval", 30)

        text = (
            f"<b>⚙️ Налаштування моніторингу</b>\n\n"
            f"🎯 <b>Моделі:</b> {models}\n"
            f"📉 <b>Мін. дисконт:</b> {min_d:.0f}%\n"
            f"📈 <b>Макс. дисконт:</b> {max_d:.0f}%\n"
            f"🕓 <b>Інтервал:</b> {interval} хв.\n"
            f"🚫 <b>Чорний список:</b> {black_list}"
        )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🎯 Редагувати моделі", callback_data="edit_models"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🚫 Редагувати Blacklist", callback_data="edit_blacklist"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="💸 Змінити поріг дисконта", callback_data="edit_score_deal"
            )
        )

        return text, builder.as_markup()
    except Exception as e:
        logging.error(f"Помилка при генерації UI налаштувань: {e}")
        return (
            "⚠️ Помилка завантаження налаштувань.",
            InlineKeyboardBuilder().as_markup(),
        )


@dp.message(Command("settings"))
async def cmd_settings(message: types.Message, config: ConfigManager) -> None:
    """Ініціює вивід головного меню налаштувань через команду."""
    try:
        text, markup = get_setting_ui(config)
        await message.answer(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logging.error(f"Помилка команди /settings: {e}")


@dp.callback_query(F.data == "settings")
async def settings_callback(
    callback: types.CallbackQuery, config: ConfigManager, state: FSMContext
) -> None:
    """Повертає користувача в головне меню налаштувань з будь-якого стану."""
    try:
        await state.clear()
        text, markup = get_setting_ui(config)
        await callback.message.edit_text(
            text=text, reply_markup=markup, parse_mode="HTML"
        )
    except TelegramBadRequest:
        await callback.answer()
    except Exception as e:
        logging.error(f"Помилка повернення до налаштувань: {e}")


@dp.callback_query(F.data.startswith("edit"))
async def edit_menu(callback: types.CallbackQuery) -> None:
    """Навігація по підменю редагування (моделі/чорний список)."""
    try:
        action = callback.data.split("_")[1]
        builder = InlineKeyboardBuilder()
        back_btn = InlineKeyboardButton(text="⬆️ Повернутися", callback_data="settings")

        if action == "models":
            builder.row(
                InlineKeyboardButton(
                    text="📲 Додати моделі", callback_data="models_add"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="🗑 Видалити моделі", callback_data="models_remove"
                )
            )
            msg = "🛠 <b>Керування моделями:</b>\nНапишіть нові або видаліть існуючі моделі."
        elif action == "blacklist":
            builder.row(
                InlineKeyboardButton(
                    text="🚫 Додати слова", callback_data="blacklist_add"
                )
            )
            builder.add(
                InlineKeyboardButton(
                    text="❎ Прибрати слова", callback_data="blacklist_remove"
                )
            )
            msg = "🛠 <b>Керування чорним списком:</b>\nСлова, які бот ігноруватиме."
        else:
            await callback.answer("Ця функція в розробці 🛠")
            return

        builder.row(back_btn)
        await callback.message.edit_text(
            msg, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Помилка в edit_menu: {e}")


@dp.callback_query(F.data.startswith("blacklist"))
@dp.callback_query(F.data.startswith("models"))
async def start_editing_fsm(callback: types.CallbackQuery, state: FSMContext):
    """Встановлює стан FSM для очікування вводу від користувача."""
    try:
        editing_type, action = callback.data.split("_")

        prompt = "додати" if action == "add" else "видалити"
        target = "моделі" if editing_type == "models" else "слова для ч/с"

        instr_msg = await callback.message.edit_text(
            f"📝 Введіть {target}, які хочете <b>{prompt}</b> (через кому):",
            parse_mode="HTML",
        )

        await state.update_data(
            editing_type=editing_type, msg_id=instr_msg.message_id, action_mode=action
        )
        await state.set_state(
            SettingsStates.add if action == "add" else SettingsStates.remove
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"По its помилка FSM старту: {e}")


@dp.message(SettingsStates.add)
@dp.message(SettingsStates.remove)
async def process_input(message: types.Message, state: FSMContext, bot: Bot) -> None:
    """Обробляє текстовий ввід користувача, готуючи зміни до підтвердження."""
    try:
        user_input = [w.strip() for w in message.text.split(",") if w.strip()]

        if not user_input:
            await message.answer("❌ Будь ласка, введіть хоча б одне слово.")

            return

        current_state = await state.get_state()
        data = await state.get_data()

        editing_type = data.get("editing_type")
        title_msg_id = data.get("msg_id")

        action_text = "додавання" if "add" in str(current_state) else "видалення"
        target_text = (
            "чорного списку" if editing_type == "blacklist" else "списку моделей"
        )

        await state.update_data(user_input=user_input)

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Підтверджую", callback_data="save_config")
        )
        builder.add(InlineKeyboardButton(text="❌ Скасувати", callback_data="settings"))

        try:
            await message.delete()
        except TelegramBadRequest as e:
            logging.warning(f"Error while deleting message ({type(e).__name__}): {e}")

        confirm_text = (
            f"❓ Підтверджуєте <b>{action_text}</b> таких слів для {target_text}?\n\n"
            f"<code>{', '.join(user_input)}</code>"
        )

        await bot.edit_message_text(
            text=confirm_text,
            chat_id=message.chat.id,
            message_id=title_msg_id,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        logging.error(f"Помилка обробки вводу FSM: {e}")


@dp.callback_query(F.data == "save_config")
async def save_config_final(
    callback: types.CallbackQuery, state: FSMContext, config: ConfigManager
) -> None:
    """Фіналізує зміни в ConfigManager та зберігає файл."""
    try:
        data = await state.get_data()
        user_input = data.get("user_input")
        action = data.get("action_mode")
        editing_type = data.get("editing_type")

        if action == "add":
            config.add(editing_type, user_input)
        else:
            config.remove(editing_type, user_input)

        config.save()

        await callback.message.edit_text(
            "✅ Конфігурацію оновлено!\nПовернення в меню через 3 сек..."
        )

        await state.clear()
        await asyncio.sleep(3)

        text, markup = get_setting_ui(config)
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Критична помилка збереження конфігу: {e}")
        await callback.message.edit_text("❌ Помилка при записі у файл.")
        await asyncio.sleep(2)
        await settings_callback(callback, config, state)


### Блок хендлерів для обробки команди /scan ###


@dp.message(Command("scan"))
async def cmd_scan(message: types.Message) -> None:
    """Викликає меню підтвердження для ручного запуску сканування."""
    try:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Так, погнали!", callback_data="process_scan"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data="close"),
        )
        await message.answer(
            "Підтвердіть запуск повного сканування ринку. Це може зайняти від 5 до 15 хвилин.",
            reply_markup=builder.as_markup(),
        )

    except Exception as e:
        logging.error(f"Помилка в cmd_scan: {e}")


@dp.callback_query(F.data == "process_scan")
async def process_scan(callback: types.CallbackQuery, laptops: LaptopBase) -> None:
    """Запускає скрапер у фоновому потоці, щоб не блокувати роботу бота."""
    try:
        from scraper import run_scraper
        from analysis_engine import find_hot_deals

        await callback.message.edit_text(
            text="🔍 <b>Пошук почався...</b>\nЯ перевіряю OLX на наявність нових ноутбуків. Як тільки закінчу — покажу результат.",
            parse_mode="HTML",
        )

        success = await asyncio.to_thread(run_scraper)

        if success:
            await asyncio.to_thread(find_hot_deals)

            laptops.update()

            if not laptops.df.empty and "is_new" in laptops.df.columns:
                laptops.df = laptops.df.sort_values(by="is_new", ascending=False)
                laptops.df.reset_index(drop=True, inplace=True)
                logging.info("Дані відсортовані: нові оголошення вгорі.")

            logging.info(
                f"Серед них нових: {len(laptops.df[laptops.df['is_new']])}!"
            )

            if len(laptops) > 0:
                index = laptops.get_valid_index(0)
                await callback.message.delete()
                await show_laptop_card(callback.message, index, laptops)
            else:
                await callback.message.edit_text(
                    "✅ Сканування завершено, але нових вигідних пропозицій поки немає."
                )
        else:
            logging.error("Скрапер повернув False під час виконання.")
            await callback.message.edit_text(
                "❌ Не вдалося оновити базу даних. Перевірте з'єднання з мережею."
            )

    except Exception as e:
        logging.error(f"Критична помилка під час сканування: {e}")
        await callback.message.edit_text(
            "⚠️ Сталася помилка під час сканування. Подробиці в логах."
        )


@dp.callback_query(F.data == "close")
async def close(callback: types.CallbackQuery) -> None:
    """Видаляє поточне повідомлення та попереднє (якщо воно було)."""
    try:
        chat_id = callback.message.chat.id
        current_msg_id = callback.message.message_id

        try:
            await callback.bot.delete_message(
                chat_id=chat_id, message_id=current_msg_id - 1
            )
        except Exception:
            pass

        await callback.message.delete()
    except Exception as e:
        logging.error(f"Помилка при закритті меню: {e}")


### Функція оповіщення про нові пропозиції ###


async def notify_users_new_deals(
    bot: Bot, config: ConfigManager, laptops: LaptopBase
) -> None:
    """
    Функція для фонового планувальника (scheduler).
    Надсилає повідомлення-тригер, якщо знайдено нові ноутбуки.
    """
    try:
        laptops.update()

        chat_id = config.data.get("chat_id")
        if not chat_id:
            logging.warning(
                "Сповіщення не надіслано: chat_id не встановлено в конфігу."
            )
            return

        new_count = (
            len(laptops.df[laptops.df["is_new"]]) if not laptops.df.empty else 0
        )

        if new_count > 0:
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔥 Переглянути нові знахідки", callback_data=f"next:{0}"
                )
            )

            await bot.send_message(
                chat_id=chat_id,
                text=f"📢 <b>Знайдено {new_count} нових вигідних пропозицій!</b>\nНатисніть кнопку нижче, щоб переглянути.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
            logging.info(f"Надіслано сповіщення про {new_count} нових ноутбуків.")

    except Exception as e:
        logging.error(f"Помилка в notify_users_new_deals: {e}")


async def main():

    laptops = LaptopBase("data/hot_deals.csv")

    config = ConfigManager()

    TOKEN = config.data["token"]

    bot = Bot(token=TOKEN)

    app_data = {"laptops": laptops, "config": config}

    await dp.start_polling(bot, **app_data)


if __name__ == "__main__":
    asyncio.run(main())
