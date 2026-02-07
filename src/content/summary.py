import os
import re
import io
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import PyPDF2
from trafilatura import fetch_url, extract
from trafilatura.settings import DEFAULT_CONFIG
from copy import deepcopy
import logging
from litellm import acompletion
from src.utils.constants import MIN_TEXT_LENGTH_FOR_SUMMARY
logger = logging.getLogger('discord')  # Get the discord logger

GEMINI_SCRAPER_MODEL = os.getenv("GEMINI_SCRAPER_MODEL", "openrouter/google/gemini-3-flash-preview")

# File extensions that cannot be summarised
UNSUMMARISABLE_EXTENSIONS = frozenset([
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff',
    # Audio
    '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a',
    # Video
    '.mp4', '.webm', '.avi', '.mov', '.mkv', '.wmv', '.flv',
    # Archives/binary
    '.zip', '.rar', '.7z', '.tar', '.gz', '.exe', '.dmg', '.apk',
])

# Domains that host primarily media content
MEDIA_HOSTING_DOMAINS = frozenset([
    'imgur.com', 'i.imgur.com',
    'giphy.com', 'media.giphy.com',
    'tenor.com', 'media.tenor.com',
    'gfycat.com', 'streamable.com',
    'v.redd.it', 'i.redd.it',
    'pbs.twimg.com',
    'media.discordapp.net', 'cdn.discordapp.com',
])


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL."""
    return '//www.youtube.com/' in url or '//youtu.be/' in url


def is_summarisable_url(url: str) -> bool:
    """Check if URL is likely to contain text content worth summarising."""
    url_lower = url.lower()
    path = url_lower.split('?')[0].split('#')[0]

    # Check file extension
    for ext in UNSUMMARISABLE_EXTENSIONS:
        if path.endswith(ext):
            return False

    # Check media hosting domains
    try:
        domain = url_lower.replace('https://', '').replace('http://', '').split('/')[0].split(':')[0]
        for media_domain in MEDIA_HOSTING_DOMAINS:
            if domain == media_domain or domain.endswith('.' + media_domain):
                return False
    except Exception:
        pass

    return True

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
    if is_youtube_url(url):
        video_id, trailing_text = extract_video_id_and_trailing_text(url.strip("<>"))
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)
        except Exception as e:
            logger.info(f"Error getting transcript for {video_id}: {e}")
            return "Sorry, I couldn't get a transcript for that video."
        transcript_text = ""
        for snippet in transcript_list:
            transcript_text += snippet.text + "\n"
        page_text = transcript_text.strip()
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

    # Validate we have meaningful text content
    if page_text and len(page_text.strip()) < MIN_TEXT_LENGTH_FOR_SUMMARY:
        logger.info(f"Extracted text too short ({len(page_text.strip())} chars) for {url}")
        return None

    return page_text


async def summarise_with_gemini(url: str, prompt: str) -> str | None:
    """Use Gemini's urlContext to fetch and summarise a URL directly.

    Returns the summary text, or None if unavailable or on failure.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.info("OPENROUTER_API_KEY not set, skipping Gemini URL summarisation")
        return None

    try:
        tools = [{"urlContext": {}}]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant who specialises in providing concise, "
                    "short summaries of web pages for Discord users. Keep your summary "
                    "brief and to the point."
                ),
            },
            {
                "role": "user",
                "content": f"{prompt} :: Please summarise this URL: {url}" if prompt else f"Please summarise this URL: {url}",
            },
        ]
        response = await acompletion(
            model=GEMINI_SCRAPER_MODEL,
            messages=messages,
            tools=tools,
            temperature=1.0,
        )
        result = response.choices[0].message.content
        if result and len(result.strip()) > 0:
            logger.info(f"Gemini URL summarisation succeeded for {url}")
            return result.strip()
        logger.info("Gemini returned empty response for URL summarisation")
        return None
    except Exception as e:
        logger.warning(f"Gemini URL summarisation failed for {url}: {e}")
        return None
