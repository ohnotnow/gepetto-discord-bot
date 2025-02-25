import os
import json
from enum import Enum
import anthropic
from openai.types.chat import chat_completion_message_tool_call as tool_call
from gepetto.response import ChatResponse, FunctionResponse

class Model(Enum):
    CLAUDE_3_HAIKU = ('claude-3-haiku-20240229', 0.25, 1.25)
    CLAUDE_3_SONNET = ('claude-3-sonnet-20240229', 3.00, 15.00)
    CLAUDE_35_SONNET = ('claude-3-5-sonnet-20241022', 3.00, 15.00)
    CLAUDE_37_SONNET = ('claude-3-7-sonnet-20250219', 3.00, 15.00)
    CLAUDE_35_HAIKU = ('claude-3-5-haiku-20241022', 1.00, 5.00)
    # CLAUDE_35_SONNET = ('claude-3-5-sonnet-20240620', 3.00, 15.00)
    CLAUDE_3_OPUS = ('claude-3-opus-20240307', 15.00, 75.00)

def convert_openai_tools_to_anthropic(openai_tool_list):
    anthropic_tool_list = []

    for openai_tool in openai_tool_list:
        # Extract details from the OpenAI format
        openai_function = openai_tool["function"]

        # Convert to the Anthropic format
        anthropic_tool = {
            "name": openai_function["name"],
            "description": openai_function["description"],
            "input_schema": openai_function["parameters"]
        }

        # Rename the 'parameters' to 'input_schema' and keep the structure
        anthropic_tool["input_schema"]["required"] = openai_function["parameters"]["required"]
        anthropic_tool_list.append(anthropic_tool)

    return anthropic_tool_list

def anthropic_tool_call_to_openai(anthropic_tool_call):
    tool = tool_call.ChatCompletionMessageToolCall(
        function=tool_call.Function(name=anthropic_tool_call.name, arguments=json.dumps(anthropic_tool_call.input)),
        id="made-up-id",
        type="function"
    )
    return tool

class ClaudeModel():
    name = "Minxie"
    uses_logs = False
    model = 'claude-3-7-sonnet-20250219'


    def get_token_price(self, token_count, direction="output", model_engine=None):
        token_price_input = 0
        token_price_output = 0
        if not model_engine:
            model_engine = self.model
        for model in Model:
            if model_engine == model.value[0]:
                token_price_input = model.value[1] / 1000000
                token_price_output = model.value[2] / 1000000
                break
        if direction == "input":
            return round(token_price_input * token_count, 4)
        return round(token_price_output * token_count, 4)

    async def chat(self, messages, temperature=0.7, model=None, json_mode=False, tools=[]):
        """Chat with the model.

        Args:
            messages (list): The messages to send to the model.
            temperature (float): The temperature to use for the model.

        Returns:
            str: The response from the model.
            tokens: The number of tokens used.
            cost: The estimated cost of the request.
        """
        if not model:
            model = self.model
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
        params = {
            "model": model,
            "max_tokens": 1000,
            "temperature": temperature,
            "system": system_prompt,
            "messages": claude_messages
        }
        if tools:
            tools = convert_openai_tools_to_anthropic(tools)
            params["tools"] = tools
        response = client.messages.create(**params)
        tokens = response.usage.input_tokens + response.usage.output_tokens
        cost = self.get_token_price(tokens, "output", model) + self.get_token_price(response.usage.input_tokens, "input", model)
        message = str(response.content[0].text)
        tool_calls = []
        if response.stop_reason == "tool_use":
            for content in response.content:
                if content.type == "tool_use":
                    tool_calls.append(anthropic_tool_call_to_openai(content))
        return ChatResponse(message, tokens, cost, model, tool_calls=tool_calls)

    async def function_call(self, messages = [], tools = [], temperature=0.7, model="mistralai/Mistral-7B-Instruct-v0.1"):
        raise NotImplementedError
