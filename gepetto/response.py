

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
