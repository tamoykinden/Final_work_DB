import telebot
import requests

TOKEN = "telebot_token"
bot = telebot.TeleBot(TOKEN)


YANDEX_TOKEN = 'YANDEX_TOKEN'
HOST_YANDEX_DISK = 'https://cloud-api.yandex.net:443'


@bot.message_handler(commands=['create_folder'])
def create_folder_handler(message):
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, 'Введите название папки')
    bot.register_next_step_handler(msg, create_folder)


def create_folder(message):
    path = message.text
    headers = {'Authorization': 'OAuth %s' % YANDEX_TOKEN}
    request_url = HOST_YANDEX_DISK + '/v1/disk/resources?path=%s' % path
    response = requests.put(url=request_url, headers=headers)
    if response.status_code == 201:
        bot.reply_to(message, "Я создал папку %s" % path)
    else:
        bot.reply_to(message, '\n'.join(["Произошла ошибка. Текст ошибки", response.text]))


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет. Я учебный бот Нетологии")


@bot.message_handler(commands=['help'])
def send_welcome(message):
    bot.reply_to(message, "Вы вызвали команду help. Но я ещё ничего не умею")


if __name__ == '__main__':
    print('Бот запущен...')
    print('Для завершения нажмите Ctrl+Z')
    bot.polling()
