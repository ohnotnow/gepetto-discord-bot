from enum import Enum
import json
from litellm import completion, acompletion
import litellm
from gepetto.response import ChatResponse, FunctionResponse
from typing import List, Dict, Any, Optional, Tuple
import os
import time
class BaseModel:
    uses_logs: bool = True
    default_model: str = os.getenv("BOT_MODEL", "gpt-4o-mini")
    provider: str = os.getenv("BOT_PROVIDER", "openai")
    omnilistens: bool = False

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.default_model
        self.name = os.getenv("BOT_NAME", "Base")
        self.omnilistens = os.getenv("BOT_OMNILISTENS", "false").lower() == "true"

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
        # litellm._turn_on_debug()

        litellm.drop_params = True
        model = self.get_model_string(model)
        print(f"Using model: {model}")
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "reasoning_effort": "low",
        }
        if self.model.startswith("openai/"):
            params["verbosity"] = "low"

        if json_mode:
            params["response_format"] = {"type": "json_object"}

        if tools and self.model_supports_tools(model):
            print(f"Using tools: {tools} with model: {model}")
            params["tools"] = tools
            params["tool_choice"] = "auto"

        if "gemini" in model:
            params["safety_settings"] = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                },
            ]


        start_time = time.time()
        response = await acompletion(**params)
        end_time = time.time()
        duration = end_time - start_time
        try:
            cost = round(response._hidden_params["response_cost"], 5)
        except:
            cost = 0
        tokens = response.usage.total_tokens
        message = str(response.choices[0].message.content)
        tool_calls = response.choices[0].message.tool_calls
        # check if we have model 'reasoning'
        reasoning_content = getattr(response.choices[0].message, "reasoning_content", None)
        return ChatResponse(message, tokens, cost, model, tool_calls=tool_calls, reasoning_content=reasoning_content, duration=duration)

    def model_supports_tools(self, model: str) -> bool:
        models_with_tools = ["openai", "anthropic"]
        return any(m in model for m in models_with_tools)

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
