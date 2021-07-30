from string import punctuation as FORBIDDEN_CHARACTERS

import youtube_dl
from youtubesearchpython import VideosSearch

SEARCH_LIMIT = 10
MAX_RETRY_COUNT = 3


def get_download_code(link):
    with youtube_dl.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(link, download=False)
        formats = info_dict['formats']
        # First, try to find m4a file
        for i in formats:
            if i['ext'] == 'm4a':
                return i['format_id']
        # Else fuck it we're gonna download the music as webm
        return formats[0]['format_id']


def download_as_audio(link, file_title, retry_count=0):
    try:
        sec_file_name = secure_filename(file_title)

        d_code = get_download_code(link)

        options = {
            'outtmpl': sec_file_name,
            'format': 'bestaudio/{}'.format(d_code),
        }

        with youtube_dl.YoutubeDL(options) as ydl:
            ydl.download([link])

        return open(sec_file_name, 'rb')
    except Exception as e:
        if retry_count > MAX_RETRY_COUNT:
            print('Couldn\'t download a video!', link, e)
        else:
            return download_as_audio(link, file_title, retry_count + 1)


def get_audio_size(link):
    with youtube_dl.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(link, download=False)
        formats = info_dict['formats']
        # First, try to find m4a file

    for i in formats:
        if i['ext'] == 'm4a':
            return i['filesize'] / 1024 / 1024
    return formats[0]['filesize'] / 1024 / 1024  # <- In case no m4a source was found


def search(request, page):
    search_results = VideosSearch(request, limit=SEARCH_LIMIT, region='US')
    res = {}

    i = 1
    while i != page:
        i += 1
        search_results.next()

    for i in search_results.result()['result']:
        if i['duration']:  # If it's a live stream we'll skip it
            res[i['title']] = i['link']
    return res


def get_video_info(url: str):
    with youtube_dl.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        return info_dict


def secure_filename(file_name: str) -> str:
    # Replace special characters
    for i in FORBIDDEN_CHARACTERS:
        file_name = file_name.replace(i, '_')
    return file_name


def get_link_from_msg(text: str):
    words = text.split()
    res = ''
    for i in words:
        if 'youtu.be' in i:
            res = i[i.rfind('/') + 1:]
        elif 'youtube.com' in i:
            needed_substring = 'watch?v='
            res = i[i.find(needed_substring) + len(needed_substring):]
    if res:
        return 'https://www.youtube.com/watch?v=' + res.split('&')[0].split('?')[0]  # If video has
        # .../watch?v=...&list=...
    return None


def get_video_code(link: str):
    return link.split('youtube.com/watch?v=')[-1]