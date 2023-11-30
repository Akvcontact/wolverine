import logging
from pyrogram.errors import InputUserDeactivated, FloodWait, UserIsBlocked, PeerIdInvalid
from info import MAX_LIST_ELM, FORCESUB_CHANNEL, ADMINS
from imdb import Cinemagoer
import asyncio
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import enums
from typing import Union
import re
import os
from typing import List
from database.users_chats_db import db
from bs4 import BeautifulSoup
import aiohttp
from urllib.parse import quote_plus
import base64

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\((buttonurl|buttonalert):(?:/{0,2})(.+?)(:same)?\))"
)

imdb = Cinemagoer()

BANNED = {}
SMART_OPEN = '“'
SMART_CLOSE = '”'
START_CHAR = ('\'', '"', SMART_OPEN)

# temp db for banned 
class temp(object):
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT=int(os.environ.get("SKIP", 2))
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    SETTINGS = {}

async def is_subscribed(bot, query):
    if not FORCESUB_CHANNEL:
        return True
    if query.from_user.id in ADMINS:
        return True
    try:
        if await db.is_user_joined(query.from_user.id)==True:
            return True
    except Exception as e:
        logger.exception(e)
        pass
    return False
    

async def broadcast_messages(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await broadcast_messages(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} -Blocked the bot.")
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        return False, "Error"


# search engine
async def search_gagala(text):
    usr_agent = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/61.0.3163.100 Safari/537.36'
    }
    text = quote_plus(text)

    async def fetch(url, session, params=None):
        async with session.get(url, params=params) as response:
            return await response.text()

    async with aiohttp.ClientSession(headers=usr_agent) as session:
        # Try searching with Google
        html_content = await fetch(f'https://www.google.com/search?q={text}', session)
        soup = BeautifulSoup(html_content, 'html.parser')
        results = [title.getText() for title in soup.find_all('h3')]

        # If no results, try searching with Yahoo
        if not results:
            html_content = await fetch(f'https://search.yahoo.com/search?q={text}', session)
            soup = BeautifulSoup(html_content, 'html.parser')
            titles = soup.find_all('a', class_='d-ib fz-20 lh-26 td-hu tc va-bot mxw-100p')
            results = [kit.contents[1] for kit in titles]

        # If still no results, try searching with Brave
        if not results:
            params = {'q': text, 'source': 'web', 'tf': 'at', 'offset': 0}
            while True:
                html_content = await fetch('https://search.brave.com/search', session, params)
                soup = BeautifulSoup(html_content, 'lxml')

                if soup.select_one('.ml-15'):
                    params['offset'] += 1
                else:
                    break

                results.extend([result.select_one('.snippet-title').get_text().strip() for result in soup.select('.snippet')])

        return results


def get_size(size):
    """Get size in readable format"""

    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def split_list(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]  

def get_file_id(msg: Message):
    if msg.media:
        for message_type in (
            "photo",
            "animation",
            "audio",
            "document",
            "video",
            "video_note",
            "voice",
            "sticker"
        ):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj

def extract_user(message: Message) -> Union[int, str]:
    user_id = None
    user_first_name = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name

    elif len(message.command) > 1:
        if (
            len(message.entities) > 1 and
            message.entities[1].type == enums.MessageEntityType.TEXT_MENTION
        ):
           
            required_entity = message.entities[1]
            user_id = required_entity.user.id
            user_first_name = required_entity.user.first_name
        else:
            user_id = message.command[1]
            # don't want to make a request -_-
            user_first_name = user_id
        try:
            user_id = int(user_id)
        except ValueError:
            pass
    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    return (user_id, user_first_name)

def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    elif MAX_LIST_ELM:
        k = k[:int(MAX_LIST_ELM)]
        return ' '.join(f'{elem}, ' for elem in k)
    else:
        return ' '.join(f'{elem}, ' for elem in k)

def last_online(from_user):
    time = ""
    if from_user.is_bot:
        time += "🤖 Bot :("
    elif from_user.status == enums.UserStatus.RECENTLY:
        time += "Recently"
    elif from_user.status == enums.UserStatus.LAST_WEEK:
        time += "Within the last week"
    elif from_user.status == enums.UserStatus.LAST_MONTH:
        time += "Within the last month"
    elif from_user.status == enums.UserStatus.LONG_AGO:
        time += "A long time ago :("
    elif from_user.status == enums.UserStatus.ONLINE:
        time += "Currently Online"
    elif from_user.status == enums.UserStatus.OFFLINE:
        time += from_user.last_online_date.strftime("%a, %d %b %Y, %H:%M:%S")
    return time


def split_quotes(text: str) -> List:
    if not any(text.startswith(char) for char in START_CHAR):
        return text.split(None, 1)
    counter = 1  # ignore first char -> is some kind of quote
    while counter < len(text):
        if text[counter] == "\\":
            counter += 1
        elif text[counter] == text[0] or (text[0] == SMART_OPEN and text[counter] == SMART_CLOSE):
            break
        counter += 1
    else:
        return text.split(None, 1)

    # 1 to avoid starting quote, and counter is exclusive so avoids ending
    key = remove_escapes(text[1:counter].strip())
    # index will be in range, or `else` would have been executed and returned
    rest = text[counter + 1:].strip()
    if not key:
        key = text[0] + text[0]
    return list(filter(None, [key, rest]))

def parser(text, keyword):
    if "buttonalert" in text:
        text = (text.replace("\n", "\\n").replace("\t", "\\t"))
    buttons = []
    note_data = ""
    prev = 0
    i = 0
    alerts = []
    for match in BTN_URL_REGEX.finditer(text):
        # Check if btnurl is escaped
        n_escapes = 0
        to_check = match.start(1) - 1
        while to_check > 0 and text[to_check] == "\\":
            n_escapes += 1
            to_check -= 1

        # if even, not escaped -> create button
        if n_escapes % 2 == 0:
            note_data += text[prev:match.start(1)]
            prev = match.end(1)
            if match.group(3) == "buttonalert":
                # create a thruple with button label, url, and newline status
                if bool(match.group(5)) and buttons:
                    buttons[-1].append(InlineKeyboardButton(
                        text=match.group(2),
                        callback_data=f"alertmessage:{i}:{keyword}"
                    ))
                else:
                    buttons.append([InlineKeyboardButton(
                        text=match.group(2),
                        callback_data=f"alertmessage:{i}:{keyword}"
                    )])
                i += 1
                alerts.append(match.group(4))
            elif bool(match.group(5)) and buttons:
                buttons[-1].append(InlineKeyboardButton(
                    text=match.group(2),
                    url=match.group(4).replace(" ", "")
                ))
            else:
                buttons.append([InlineKeyboardButton(
                    text=match.group(2),
                    url=match.group(4).replace(" ", "")
                )])

        else:
            note_data += text[prev:to_check]
            prev = match.start(1) - 1
    else:
        note_data += text[prev:]

    try:
        return note_data, buttons, alerts
    except:
        return note_data, buttons, None

def remove_escapes(text: str) -> str:
    res = ""
    is_escaped = False
    for counter in range(len(text)):
        if is_escaped:
            res += text[counter]
            is_escaped = False
        elif text[counter] == "\\":
            is_escaped = True
        else:
            res += text[counter]
    return res


def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'



async def replace_blacklist(file_name, blacklist, remove_emojis=True, remove_special_chars=False, remove_links=True):
    for word in blacklist:
        file_name = re.sub(re.escape(word), "", file_name, flags=re.IGNORECASE)

    if remove_emojis:
        emoticon_pattern = re.compile(u'[\U0001F600-\U0001F64F]|\U0001F923|\U0001F602|\U0001F603|\U0001F604|\U0001F605|\U0001F606|\U0001F609|\U0001F60A|\U0001F60B|\U0001F60E|\U0001F60D|\U0001F618|\U0001F617|\U0001F619|\U0001F61A|\U0001F61C|\U0001F61D|\U0001F61B|\U0001F911|\U0001F917|\U0001F913|\U0001F60F|\U0001F612|\U0001F61E|\U0001F614|\U0001F61F|\U0001F615|\U0001F641|\U0001F642|\U0001F9D0-\U0001F9D2|\U0001F970|\U0001F60C|\U0001F61C|\U0001F92A|\U0001F92D]+')
        file_name = emoticon_pattern.sub('', file_name)

    if remove_special_chars:
        file_name = re.sub(r'[^a-zA-Z0-9\s]', '', file_name)
        
    if remove_links:
        file_name = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', file_name)

    return file_name


# To fetch random Quotes
async def fetch_quote_content():
    url = "https://api.quotable.io/quotes/random"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                quote_data = await response.json()
                
                # Check if the response is a list of quotes
                if isinstance(quote_data, list) and len(quote_data) > 0:
                    quote = quote_data[0]
                    return quote.get("content", None)
                
                # If not a list, assume it's a single quote
                return quote_data.get("content", None)
            else:
                return None

def encode_to_base64(text):
    encoded_data = base64.urlsafe_b64encode(text.encode('utf-8')).rstrip(b'=').decode('utf-8')
    return encoded_data

def decode_from_base64(text):
    decoded_data = base64.urlsafe_b64decode(text.encode('utf-8'))
    return decoded_data