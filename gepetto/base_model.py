from enum import Enum
import json
from litellm import completion, acompletion
from gepetto.response import ChatResponse, FunctionResponse
from typing import List, Dict, Any, Optional, Tuple

class BaseModel:
    name: str = "Base"
    uses_logs: bool = True
    default_model: str = "gpt-4"
    provider: str = "openai"

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.default_model

    def get_model_string(self, model: Optional[str] = None) -> str:
        """Convert model name to LiteLLM format"""
        use_model = model or self.model
        return f"{self.provider}/{use_model}"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        model: Optional[str] = None,
        top_p: float = 0.6,
        json_mode: bool = False,
        tools: List[Dict[str, Any]] = []
    ) -> ChatResponse:
        """Generic chat implementation using LiteLLM"""
        model = self.get_model_string(model)
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if json_mode:
            params["response_format"] = {"type": "json_object"}

        if tools and not model.startswith("gemini"):
            params["tools"] = tools
            params["tool_choice"] = "auto"

        response = await acompletion(**params)

        try:
            cost = round(response._hidden_params["response_cost"], 5)
        except:
            cost = 0
        tokens = response.usage.total_tokens
        message = str(response.choices[0].message.content)
        tool_calls = response.choices[0].message.tool_calls

        return ChatResponse(message, tokens, cost, model, tool_calls=tool_calls)

    async def function_call(
        self,
        messages: List[Dict[str, str]] = [],
        tools: List[Dict[str, Any]] = [],
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> FunctionResponse:
        """Generic function call implementation using LiteLLM"""
        model = self.get_model_string(model)
        print(f"Made a function call using {model}")
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": tools[0]["function"]["name"]}},
            temperature=temperature
        )

        # Calculate cost using the completion response
        cost = self.get_token_price(completion_response=response)

        tokens = response.usage.total_tokens
        message = response.choices[0].message
        parameters = json.loads(message.tool_calls[0].function.arguments)
        return FunctionResponse(parameters, tokens, cost)
