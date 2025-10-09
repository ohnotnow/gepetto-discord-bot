import re
import io
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import PyPDF2
from trafilatura import fetch_url, extract
from trafilatura.settings import DEFAULT_CONFIG
from copy import deepcopy
import logging
logger = logging.getLogger('discord')  # Get the discord logger

request_headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-GB,en;q=0.5",
    "Connection": "keep-alive",
    "DNT": "1",
    "Priority": "u=0, i",
    "Referer": "https://duckduckgo.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "TE": "trailers",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:141.0) Gecko/20100101 Firefox/141.0"
}

def get_text_from_pdf(url: str) -> str:
    try:
        response = requests.get(url, headers=request_headers)
        file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Could not get pdf text for {url}")
        print(e)
        return "Could not extract text for this PDF.  Sorry."



def extract_video_id_and_trailing_text(input_string):
    logger.info(f"Extracting video ID and trailing text for {input_string}")
    # Use a regular expression to match a YouTube URL and extract the video ID
    video_id_match = re.search(r"https://www\.youtube\.com/watch\?v=([^&\s\?]+)", input_string)
    video_id = video_id_match.group(1) if video_id_match else None

    # If a video ID was found, remove the URL from the string to get the trailing text
    if video_id:
        url = video_id_match.group(0)  # The entire matched URL
        trailing_text = input_string.replace(url, '').strip()
    else:
        trailing_text = ''
    logger.info(f"Video ID: {video_id} - Trailing text: {trailing_text}")
    return video_id, trailing_text

async def get_text(url: str) -> str:
    page_text = ""
    if '//www.youtube.com/' in url:
        video_id, trailing_text = extract_video_id_and_trailing_text(url.strip("<>"))
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)
        except Exception as e:
            logger.info(f"Error getting transcript for {video_id}: {e}")
            return "Sorry, I couldn't get a transcript for that video."
        transcript_text = [x['text'] for x in transcript_list]
        page_text = ' '.join(transcript_text)
        if "The copyright belongs to Google LLC" in page_text:
            page_text = "Could not get the transcript - possibly I am being geoblocked"

    else:
        url_match = re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url)
        url_string = url_match.group(0) if url_match else None

        if not url_string:
            return "Sorry, I couldn't find a URL in that message."

        # If a URL was found, remove it from the string to get the trailing text
        if url_string:
            url_string = url_string.strip('<>')
            trailing_text = url.replace(url_string, '').strip()
            if trailing_text:
                prompt = trailing_text
        if url_string.endswith('.pdf'):
            page_text = get_text_from_pdf(url_string)
        else:
            my_config = deepcopy(DEFAULT_CONFIG)
            # insert all of the custom request_headers into the config
            for key, value in request_headers.items():
                my_config['DEFAULT'][key] = value
            downloaded = fetch_url(url_string, config=my_config)
            if downloaded is None:
                return f"Sorry, I couldn't download content from the URL {url_string}."
            page_text = extract(downloaded)

    return page_text
