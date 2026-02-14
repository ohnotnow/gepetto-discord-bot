

class ChatResponse:
    """A response from the API.

    Attributes:
        message (str): The message from the API.
        tokens (int): The number of tokens used.
        cost (float): The estimated cost of the request in USD.
        model (str): The model used to generate the response.
        duration (float): The duration of the request in seconds.
        tokens_per_second (float): The number of tokens per second.
    """
    def __init__(self, message, tokens, cost, model="Unknown", uses_logs=False, tool_calls=None, reasoning_content=None, duration=None, completion_tokens=None):
        self.message = message
        self.tokens = tokens
        self.cost = cost
        self.duration = round(duration, 2) if duration else 'N/A'
        self.tokens_per_second = round(completion_tokens / duration, 2) if completion_tokens and duration else None
        self.usage = f"_[Tokens used: {self.tokens} | Estimated cost US${round(self.cost, 5)} | Model: {model}] | Tokens per second: {self.tokens_per_second} | Duration: {self.duration} seconds |_"
        self.usage_short = f"_[Model: {model} | Tokens per second: {self.tokens_per_second}]_"
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content

    def __str__(self):
        return f"{self.message}\n{self.usage}"

class FunctionResponse:
    """A function call response from the API.

    Attributes:
        parameters (dict): The parameters returned from the function call
        tokens (int): The number of tokens used.
        cost (float): The estimated cost of the request in USD.
    """
    def __init__(self, parameters, tokens, cost):
        self.parameters = parameters
        self.tokens = tokens
        self.cost = cost
        self.usage = f"_[tokens used: {self.tokens} | Estimated cost US${round(self.cost, 5)}]_"

    def __str__(self):
        return f"{self.parameters}\n{self.usage}"

import re
from typing import List

# Forward-looking sentence boundary: punctuation + optional closing quote/bracket + whitespace
SENTENCE_BOUNDARY = re.compile(r'([.!?][\"\')\]]?)\s+')

def split_for_discord(
    text: str,
    limit: int = 1800,
    preserve_code_fences: bool = True,
) -> List[str]:
    """
    Split `text` into chunks <= `limit` characters, preferring to split on:
    1) double newlines, 2) single newlines, 3) sentence boundaries, 4) spaces,
    with a hard split as last resort.

    If `preserve_code_fences` is True, it tries not to leave an unmatched ``` in a chunk.
    When that happens, it closes the fence at the end of the chunk and reopens it
    at the start of the next chunk.
    """
    if not text:
        return [""]

    # If we'll sometimes add closing/reopening ``` around boundaries, keep headroom.
    effective_limit = limit - 6 if preserve_code_fences else limit

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= effective_limit:
            candidate = remaining
            remaining = ""
        else:
            window = remaining[:effective_limit + 1]

            # Priority 1: paragraph break
            cut = window.rfind("\n\n")

            # Priority 2: single newline
            if cut == -1:
                cut = window.rfind("\n")

            # Priority 3: sentence boundary (punct + optional closer + spaces)
            if cut == -1:
                last_m = None
                for m in SENTENCE_BOUNDARY.finditer(window):
                    last_m = m
                if last_m:
                    # Cut right after the punctuation/closer and the following spaces
                    cut = last_m.end()

            # Priority 4: space
            if cut == -1:
                cut = window.rfind(" ")

            # Fallback: hard split
            if cut == -1 or cut == 0:
                cut = effective_limit

            candidate = remaining[:cut].rstrip()
            remaining = remaining[cut:].lstrip()

        if preserve_code_fences and candidate:
            # Count ``` occurrences to detect open fence
            fence_count = candidate.count("```")
            if fence_count % 2 == 1:
                # Try to pull a closing ``` from the start of the remainder if it fits
                extra_room = effective_limit - len(candidate)
                if extra_room > 0 and remaining:
                    idx = remaining.find("```")
                    if 0 <= idx <= extra_room:
                        candidate += remaining[:idx + 3]
                        remaining = remaining[idx + 3:].lstrip()
                    else:
                        candidate += "\n```"
                        remaining = "```" + remaining

        chunks.append(candidate)

    # Ensure nothing slipped past the hard limit (very rare)
    final: List[str] = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i:i+limit])

    return final
