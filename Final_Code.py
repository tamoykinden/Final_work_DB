import configparser
import telebot
from telebot import types
import random
import psycopg2
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Чтение конфигурации
configparser = configparser.ConfigParser()
configparser.read("settings.ini")

# Конфиденциальные данные
Token = configparser["Conf_Data"]["Token"]
db_name = configparser["Conf_Data"]["Database"]
username = configparser["Conf_Data"]["User"]
db_password = configparser["Conf_Data"]["Password"]

# Инициализация бота
bot = telebot.TeleBot(Token)

# Глобальные переменные для хранения истории слов
user_word_history = {}

# Функция подключения к БД
def connect_db():
    conn = psycopg2.connect(
        database=db_name,
        user=username,
        password=db_password
    )
    return conn

# Функция создания таблиц
def create_tables():
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT PRIMARY KEY,
                user_name TEXT NOT NULL,
                chat_id BIGINT NOT NULL UNIQUE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS words(
                word_id SERIAL PRIMARY KEY,
                russian_word TEXT NOT NULL,
                english_translation TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_word(
                user_word_id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                word_id INTEGER REFERENCES words(word_id),
                UNIQUE (user_id, word_id)
                );
            """)
            conn.commit()

# Функция заполнения таблицы словами
def fill_words_DB():
    initial_words = [
        ("Я", 'I'),
        ("Ты", 'You'),
        ("Мы", 'We'),
        ("Привет", 'Hello'),
        ("Имя", 'Name'),
        ("Фамилия", 'Last name'),
        ("Студент", 'Student'),
        ("Работать", 'To work'),
        ("Красивый", 'Beautiful'),
        ("Время", 'Time')
    ]
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO words (russian_word, english_translation)
                VALUES (%s, %s);
            """, initial_words)
            conn.commit()

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    chat_id = message.chat.id

    # Добавление пользователя в БД с обработкой конфликта по chat_id
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, user_name, chat_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (chat_id) DO NOTHING;
            """, (user_id, user_name, chat_id))
            conn.commit()

    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    quiz_btn = types.KeyboardButton('Квиз')
    btn_add_word = types.KeyboardButton('Добавить слово')
    btn_del_word = types.KeyboardButton('Удалить слово')
    markup.add(quiz_btn, btn_add_word, btn_del_word)

    bot.send_message(chat_id, f"Привет, {user_name}! Я учебный бот по изучению английских слов. Давай приступим!", reply_markup=markup)

# Обработчик кнопки "Квиз"
@bot.message_handler(func=lambda message: message.text == 'Квиз')
def start_quiz(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Инициализация истории слов для пользователя
    if user_id not in user_word_history:
        user_word_history[user_id] = []

    # Получаем случайное слово из базы данных
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT word_id, russian_word, english_translation
                FROM words
                WHERE word_id NOT IN (
                    SELECT word_id FROM user_word 
                    WHERE user_id = %s
                )
                ORDER BY RANDOM() LIMIT 1;
            """, (user_id,))
            word_data = cur.fetchone()
            
            if word_data:
                word_id, russian_word, correct_translation = word_data
                user_word_history[user_id].append((word_id, russian_word, correct_translation))

                # Получаем три случайных неправильных перевода
                cur.execute("""
                    SELECT english_translation
                    FROM words
                    WHERE english_translation != %s 
                    ORDER BY RANDOM() LIMIT 3;
                """, (correct_translation,))
                wrong_translations = [row[0] for row in cur.fetchall()]
                
                # Создаем варианты ответов
                options = wrong_translations + [correct_translation]
                random.shuffle(options)

                # Создаем клавиатуру
                markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                for option in options:
                    markup.add(types.KeyboardButton(option))
                markup.add(types.KeyboardButton('Дальше'), types.KeyboardButton('Назад'))

                bot.send_message(chat_id, f"Как переводится слово {russian_word}?", reply_markup=markup)
                bot.register_next_step_handler(
                    message, 
                    lambda msg: check_answer(msg, word_id, correct_translation)
                )
            else:
                bot.send_message(chat_id, "Вы изучили все слова! Добавьте новые слова с помощью команды /add_word.")

def check_answer(message, word_id, correct_translation):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_answer = message.text

    if user_answer == correct_translation:
        # Добавляем связь пользователь-слово
        with connect_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_word (user_id, word_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (user_id, word_id))
                conn.commit()

        bot.send_message(chat_id, "✅ Правильно! Молодец!")

    elif user_answer == 'Дальше':
        start_quiz(message)
    elif user_answer == 'Назад':
        if user_id in user_word_history and len(user_word_history[user_id]) > 0:
            # Удаляем текущее слово из истории
            user_word_history[user_id].pop()
            if len(user_word_history[user_id]) > 0:
                # Берем предыдущее слово
                prev_word = user_word_history[user_id][-1]
                ask_question(message.chat.id, prev_word[0], prev_word[1], prev_word[2])
            else:
                bot.send_message(chat_id, "⏮ Нет предыдущих слов")
        else:
            bot.send_message(chat_id, "⏮ История слов пуста")
    else:
        bot.send_message(chat_id, "❌ Неправильно. Попробуйте ещё раз!")

def ask_question(chat_id, word_id, russian_word, correct_translation):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT english_translation
                FROM words
                WHERE english_translation != %s 
                ORDER BY RANDOM() LIMIT 3;
            """, (correct_translation,))
            wrong_translations = [row[0] for row in cur.fetchall()]
            
            options = wrong_translations + [correct_translation]
            random.shuffle(options)

            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            for option in options:
                markup.add(types.KeyboardButton(option))
            markup.add(types.KeyboardButton('Дальше'), types.KeyboardButton('Назад'))

            bot.send_message(chat_id, f"Как переводится слово {russian_word}?", reply_markup=markup)

# Обработчик кнопки "Добавить слово"
@bot.message_handler(func=lambda message: message.text == 'Добавить слово')
def add_word(message):
    msg = bot.send_message(message.chat.id, "📝 Введите слово на русском и перевод через дефис (пример: машина-car):")
    bot.register_next_step_handler(msg, process_add_word)

def process_add_word(message):
    try:
        russian_word, english_translation = message.text.split('-')
        with connect_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO words (russian_word, english_translation)
                    VALUES (%s, %s);
                """, (russian_word.strip(), english_translation.strip()))
                conn.commit()
        bot.send_message(message.chat.id, "✅ Слово успешно добавлено!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}\nПроверьте формат ввода!")

# Обработчик кнопки "Удалить слово"
@bot.message_handler(func=lambda message: message.text == 'Удалить слово')
def delete_word(message):
    msg = bot.send_message(message.chat.id, "🗑 Введите русское слово для удаления:")
    bot.register_next_step_handler(msg, process_delete_word)

def process_delete_word(message):
    user_id = message.from_user.id
    russian_word = message.text.strip()

    try:
        with connect_db() as conn:
            with conn.cursor() as cur:
                # Находим ID слова
                cur.execute("""
                    SELECT word_id FROM words 
                    WHERE russian_word = %s;
                """, (russian_word,))
                word_data = cur.fetchone()

                if word_data:
                    word_id = word_data[0]
                    # Удаляем связь пользователь-слово
                    cur.execute("""
                        DELETE FROM user_word 
                        WHERE user_id = %s AND word_id = %s;
                    """, (user_id, word_id))
                    conn.commit()
                    bot.send_message(message.chat.id, f"✅ Слово '{russian_word}' удалено из вашего списка!")
                else:
                    bot.send_message(message.chat.id, f"⚠️ Слово '{russian_word}' не найдено")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

if __name__ == "__main__":
    # Инициализация БД
  
    # Запуск бота
    logger.info("🟢 Бот запущен")
    bot.polling(none_stop=True)