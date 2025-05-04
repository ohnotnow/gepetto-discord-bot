import re

def remove_nsfw_words(message):
    message = re.sub(r"(fuck|prick|asshole|shit|wanker|dick)", "", message)
    return message

def remove_emoji(text):
    regrex_pattern = re.compile(pattern = "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags = re.UNICODE)
    return regrex_pattern.sub(r'',text)

def truncate(text, max_length=1800, message=None):
    """
    Truncate text to max_length. If truncated, append message (if provided).
    """
    if len(text) > max_length:
        truncated = text[:max_length]
        if message:
            return f"{message}\n\n{truncated}"
        return truncated
    return text
