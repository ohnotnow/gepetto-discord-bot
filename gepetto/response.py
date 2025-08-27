

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
    def __init__(self, message, tokens, cost, model="Unknown", uses_logs=False, tool_calls=None, reasoning_content=None, duration=None):
        self.message = message
        self.tokens = tokens
        self.cost = cost
        self.duration = round(duration, 2) if duration else 'N/A'
        self.tokens_per_second = round(tokens / duration, 2) if duration else None
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

SENTENCE_SPLIT = re.compile(r'(?<=[.!?]["\')\]]?)\s+')

def split_for_discord(
    text: str,
    limit: int = 1800,
    preserve_code_fences: bool = True,
) -> List[str]:
    if not text:
        return [""]

    effective_limit = limit - 6 if preserve_code_fences else limit

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= effective_limit:
            candidate = remaining
            cut = len(candidate)
        else:
            window = remaining[:effective_limit + 1]

            cut = window.rfind("\n\n")
            if cut == -1:
                cut = window.rfind("\n")
            if cut == -1:
                m = list(SENTENCE_SPLIT.finditer(window))
                cut = m[-1].start() if m else -1
            if cut == -1:
                cut = window.rfind(" ")
            if cut == -1:
                cut = effective_limit  # hard split

            candidate = remaining[:cut].rstrip()
            remaining = remaining[cut:].lstrip()

        if len(remaining) <= effective_limit and candidate is not remaining:
            remaining = remaining

        if preserve_code_fences:
            fence_count = candidate.count("```")
            if fence_count % 2 == 1:
                extra_room = effective_limit - len(candidate)
                if extra_room > 0:
                    idx = remaining.find("```")
                    if 0 <= idx <= extra_room:
                        candidate += remaining[:idx + 3]
                        remaining = remaining[idx + 3:].lstrip()
                    else:
                        candidate += "\n```"
                        remaining = "```" + (remaining if remaining else "")

        chunks.append(candidate)

        if not remaining:
            break

        if len(chunks) > 10000:
            break

    final = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i:i+limit])
    return final
