import os
import json
import anthropic
from gepetto.response import ChatResponse, FunctionResponse
class ClaudeModel():
    name = "Minxie"
    def get_token_price(self, token_count, direction="output", model_engine="mixtral-8x7b-32768"):
        if direction == "input":
            return (3 / 1000000) * token_count
        return (15 / 1000000) * token_count

    async def chat(self, messages, temperature=0.7, model="mixtral-8x7b-32768"):
        """Chat with the model.

        Args:
            messages (list): The messages to send to the model.
            temperature (float): The temperature to use for the model.

        Returns:
            str: The response from the model.
            tokens: The number of tokens used.
            cost: The estimated cost of the request.
        """
        api_key = os.getenv("CLAUDE_API_KEY")
        client = anthropic.Anthropic(
            api_key=api_key,
        )
        claude_messages = []
        system_prompt = ""
        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"]
            else:
                claude_messages.append(message)
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            temperature=0,
            system=system_prompt,
            messages=claude_messages
        )
        print(response.content)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        cost = self.get_token_price(tokens, "output", model) + self.get_token_price(response.usage.input_tokens, "input", model)
        message = str(response.content[0].text)
        return ChatResponse(message, tokens, cost)

    async def function_call(self, messages = [], tools = [], temperature=0.7, model="mistralai/Mistral-7B-Instruct-v0.1"):
        raise NotImplementedError
