import csv
import json
import threading
from datetime import date
from os import listdir, remove
from os.path import dirname, realpath  # To get full path to python script

import telebot

from youtube_part import *

users_daily = set()
stats_date = date.today()

SCRIPT_DIR = dirname(realpath(__file__))
ADMIN_USER_ID = 777
BOT_LINK = '<insert_bot_link>'
DEBUG_MODE = 0

translations = {}  # [$PHRASE_KEY][LANG]
lang_codes = {}
file_id_db = {}

queue = []  # (user_id, video_url, msg_to_remove: unnecessary)

users: dict = {}  # users[user_id] = [lang_code, lang]

# Callback constants
CB_LANGUAGE_CHANGE = 0
CB_VIDEO_SELECT = 1
CB_PAGE_CHANGE = 2


def report_to_admin(msg):
    if msg.text:
        bot.send_message(ADMIN_USER_ID, 'Report: ' + msg.text)
        bot.send_message(msg.chat.id, translate('#REPORT_THANKS', msg.chat.id))
    else:
        bot.send_message(msg.chat.id, translate('#WRONG_REPORT_MSG', msg.chat.id))


def warn_admin(msg: str):
    bot.send_message(ADMIN_USER_ID, 'Warning: ' + msg)


def get_tg_bot_token():
    with open('TOP_SECRET', 'r') as file:
        release_token, debug_token = file.read().rstrip('\n').split('\n')
    if DEBUG_MODE:
        return debug_token
    return release_token


def remove_temp_data(file_title):
    file_title = secure_filename(file_title)
    with open('.dontremove') as f:
        dont_remove_files = [i.strip() for i in f.readlines()]

    if file_title == '.' or file_title == '*':
        return

    for i in listdir():
        if i.startswith(file_title) and i not in dont_remove_files:
            try:
                remove(i)
            except Exception as e:
                print('Error! Couldn\'t remove a file: ', e)


def create_callback_data(*args):
    res = ''
    for i in args:
        res += '{};'.format(i)
    return res[:-1]


def get_callback_data(string: str):
    return string.split(';')


def stat_user(user):
    global stats_date, users_daily
    user_id = user.id
    print(f"Got message from {user_id} whose name is {user.first_name} "
          f"and username is {user.username}, lang code={user.language_code}")

    # Daily stats
    today = date.today()
    if today > stats_date:
        bot.send_message(ADMIN_USER_ID,
                         'I: daily usage ({}): {}'.format(stats_date, len(users_daily)))
        stats_date = today
        users_daily = {user_id}
    elif user_id not in users_daily:
        users_daily.add(user_id)

    if user_id not in users:
        users[user_id] = (user.language_code, 'en')


def send_audio(user_id, video_link):
    title = ''
    try:
        video_info = get_video_info(video_link)
        video_link = get_link_from_msg(video_link)

        caption = '<a href="t.me/{}"><i>by</i></a>'.format(BOT_LINK)

        # Check if audio is already in our DB and send it if yes
        video_code = get_video_code(video_link)
        if video_code in file_id_db:
            bot.send_audio(user_id, file_id_db[video_code], caption=caption, parse_mode='html')
            return

        title = video_info['title']
        performer = video_info['uploader']

        print('D: video link is {}, title is "{}" and performer is "{}"'.format(video_link, title, performer))

        temp_msg_id = bot.send_message(user_id, translate('#STATUS_DOWNLOADING_VIDEO', user_id)).wait().id

        audio_data = download_as_audio(video_link, title)
        if audio_data:
            bot.edit_message_text(translate('#STATUS_SENDING_AUDIO', user_id), user_id, temp_msg_id)
            bot.send_chat_action(user_id, action='upload_voice')
            msg = bot.send_audio(user_id,
                                 audio_data,
                                 performer=performer,
                                 title=title,
                                 caption=caption,
                                 parse_mode='html').wait()
            bot.delete_message(user_id, temp_msg_id)
            file_id = msg.audio.file_id
            file_id_db[video_code] = file_id

            audio_data.close()
        else:
            print('E: Audio data is empty!')
            bot.send_message(user_id, "Sorry. Couldn't download the video. :(")
    finally:
        # Cleanup
        if title:
            remove_temp_data(title)


process_started = False
alive = True


def process_queue():
    while alive:
        if queue:
            i = queue.pop(0)
            user_id, video_link = i[:2]
            try:
                send_audio(user_id, video_link)
                if len(i) == 3:  # We got a message to delete
                    try:
                        bot.delete_message(user_id, i[2])
                    except Exception:  # User has removed that message
                        pass
            except Exception as e:
                bot.send_message(user_id, 'Sorry. I can\'t process this video. Please try sending another video.')
                print('ERROR:', e)


bot = telebot.AsyncTeleBot(get_tg_bot_token())


@bot.message_handler(commands=['start', 'report', 'info', 'lang', 'contact', 'stats'])
def handle_commands(message):
    user_id = message.chat.id
    stat_user(message.from_user)
    if message.text.startswith('/start'):
        bot.reply_to(message,
                     "This bot is not created for infringement of copyright laws. "
                     "By using the bot, you agree that the material you're saving <b>DOES NOT</b> infringe copyright "
                     "laws. Thank you. ",
                     parse_mode='html')
        bot.reply_to(message, translate('#START_MSG_REPLY', user_id))
    elif message.text.startswith('/report'):
        bot.send_message(user_id, translate('#REPORT_TEXT', user_id))
        bot.register_next_step_handler_by_chat_id(user_id, report_to_admin)
    elif message.text.startswith('/info'):
        bot.send_message(user_id, translate('#INFO_MSG_REPLY', user_id))
    elif message.text == '/lang':
        keyboard = telebot.types.InlineKeyboardMarkup()
        for i in lang_codes:
            key = telebot.types.InlineKeyboardButton(text=lang_codes[i], callback_data=f'{CB_LANGUAGE_CHANGE};{i}')
            keyboard.add(key)
        bot.send_message(user_id, text='Please select your language', reply_markup=keyboard)
    elif message.text == '/stats':
        reply_msg = ''
        users_lc_users = {}  # [user's lang code] = {users)
        for i in users:
            user_lang_code = users[i][0]
            users_lc_users[user_lang_code] = users_lc_users.get(user_lang_code, set()) | {i}

        sum_ = 0
        for i in users_lc_users:
            curr_users_count = len(users_lc_users[i])
            sum_ += curr_users_count
            reply_msg += f'{i}: {curr_users_count}\n'
        reply_msg += 'Overall number of users: {}\n'.format(sum_)
        bot.reply_to(message, reply_msg + 'Daily users: {}'.format(len(users_daily)))


@bot.message_handler(content_types=['text'])
def on_message_received(message):
    stat_user(message.from_user)
    user_id = message.chat.id
    msg_txt = message.text

    link = get_link_from_msg(msg_txt)
    if link:
        try:
            duration = get_video_info(link)['duration']
        except Exception:
            bot.reply_to(message, translate('#WRONG_LINK', user_id))
            return

        if duration == 0:
            bot.reply_to(message, translate('#LIVE_STREAM_ERROR', user_id))
            return

        if get_audio_size(link) > 50:
            bot.reply_to(message, translate('#MAX_FILE_SIZE_ERROR', user_id))
            return

        queue.append((user_id, link))

    else:
        bot.send_message(user_id,
                         text=translate('#SELECT_VIDEO', user_id),
                         reply_markup=get_search_result_as_keyboard(message.text, 1))


def get_search_result_as_keyboard(request, page):
    try:
        results = search(request, page)
        keyboard = telebot.types.InlineKeyboardMarkup()

        for i in results:
            key = telebot.types.InlineKeyboardButton(text=i, callback_data=create_callback_data(CB_VIDEO_SELECT,
                                                                                                results[i]))
            keyboard.add(key)

        return keyboard
    except Exception:
        return None


@bot.callback_query_handler(func=lambda call: True)
def callback_worker(call):
    user_id = call.message.chat.id
    callback_data = get_callback_data(call.data)
    callback_code = int(callback_data[0])
    callback_data = callback_data[1:]
    if callback_code == CB_LANGUAGE_CHANGE:  # Language change
        lang_code = callback_data[0]
        user_lang_code = users[user_id][0]
        users[user_id] = (user_lang_code, lang_code)
        bot.delete_message(user_id, call.message.id)
        bot.answer_callback_query(callback_query_id=call.id,
                                  show_alert=True,
                                  text=translate('#LANG_CHANGE_SUCCESS', user_id))
    elif callback_code == CB_VIDEO_SELECT:
        video_link = callback_data[0]
        if get_audio_size(video_link) > 50:
            bot.send_message(user_id, translate('#MAX_FILE_SIZE_ERROR', user_id))
            return
        queue.append((user_id, video_link, call.message.id))
        bot.answer_callback_query(callback_query_id=call.id,
                                  show_alert=True,
                                  text='Your request has been added to the queue. Please wait ❤')


def translate(phrase_code: str, user_id: int):
    user_lang = users[user_id][1]
    return translations[phrase_code][user_lang]


def load_translations():
    with open('languages.json') as f:
        data = json.load(f)
    for language in data:
        lang_name, lang_code = None, None
        for key, value in language.items():
            if key == 'translations':
                for phrase_code, translation in value.items():
                    if translations.get(phrase_code, None) is None:
                        translations[phrase_code] = {}
                    translations[phrase_code][lang_code] = translation
            else:
                lang_name, lang_code = value[0], value[1]
                lang_codes[lang_code] = lang_name
    print('D: translations & lang_codes loaded')


def load_users_db():  # user_id, lang_code, lang
    global users
    try:
        with open('users.db') as f:
            reader = csv.reader(f)
            for i in reader:
                user_id, lang_code, lang = i
                users[int(user_id)] = [lang_code, lang]
            print('D: users db loaded')
    except FileNotFoundError:
        pass


def save_users_db():
    with open('users.db', 'w') as f:
        writer = csv.writer(f)
        for i in users:
            writer.writerow([i, *users[i]])


def load_video_db():
    try:
        with open('video_database.csv', encoding='utf8') as csv_file:
            reader = csv.reader(csv_file, delimiter=';', quotechar='"')
            # CSV file format: video_url, bit_rate, file_id
            for i in reader:
                link, file_id = i
                file_id_db[link] = file_id
    except FileNotFoundError:
        pass


def save_video_db():
    with open('video_database.csv', 'w', encoding='utf8') as csv_file:
        writer = csv.writer(csv_file, delimiter=';', quotechar='"')
        # CSV file format: video_url, bit_rate, file_id
        for i in file_id_db:
            writer.writerow([i, file_id_db[i]])


# Remove old data if our program crashed
def init():
    try:
        load_translations()
        load_users_db()
        load_video_db()

    except Exception as e:
        warn_admin('Exception! {}'.format(e))

    # Start the thread
    global process_started
    if not process_started:
        print('CALLED THREAD!')
        th = threading.Thread(target=process_queue)
        th.start()
        process_started = True

    # Start the bot
    bot.polling(none_stop=True, interval=4)


try:
    init()
finally:
    alive = False  # Make 'alive' False to finish the 2nd thread of this app
    save_users_db()
    save_video_db()
