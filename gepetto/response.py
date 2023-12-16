

class ChatResponse:
    """A response from the API.

    Attributes:
        message (str): The message from the API.
        tokens (int): The number of tokens used.
        cost (float): The estimated cost of the request in USD.
    """
    def __init__(self, message, tokens, cost):
        self.message = message
        self.tokens = tokens
        self.cost = cost
        self.usage = f"_[tokens used: {self.tokens} | Estimated cost US${round(self.cost, 5)}]_"

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
