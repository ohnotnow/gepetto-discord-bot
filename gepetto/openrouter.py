import os
import json
from enum import Enum
import google.generativeai as genai
from gepetto.response import ChatResponse, FunctionResponse
from .base_model import BaseModel
from openai import OpenAI
from typing import List, Dict, Any, Optional
class OpenrouterModel(BaseModel):
    name = "RecipeThis"
    uses_logs = True
    default_model = "deepseek/deepseek-chat-v3-0324"
    provider = "openrouter"
