import os
import json
from enum import Enum
import google.generativeai as genai
from gepetto.response import ChatResponse, FunctionResponse
from .base_model import BaseModel
from openai import OpenAI
from typing import List, Dict, Any, Optional
class OpenrouterModel():
    name = "RecipeThis"
    uses_logs = True
    default_model = "quasar-alpha"
    provider = "openrouter"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        model: Optional[str] = None,
        top_p: float = 0.6,
        json_mode: bool = False,
        tools: List[Dict[str, Any]] = []
    ) -> ChatResponse:
        """Generic chat implementation using the OpenAI-compat openrouter API"""
        model = self.get_model_string(model)
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if json_mode:
            params["response_format"] = {"type": "json_object"}

        if tools and not (model.startswith("gemini") or model.startswith("openrouter")):
            params["tools"] = tools
            params["tool_choice"] = "auto"

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        cost = 0
        tokens = completion.usage.total_tokens
        message = completion.choices[0].message.content
        tool_calls = []


        return ChatResponse(message, tokens, cost, model, tool_calls=tool_calls)
