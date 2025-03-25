import os
import json
from enum import Enum
import google.generativeai as genai
from gepetto.response import ChatResponse, FunctionResponse
from .base_model import BaseModel

class GeminiModel(BaseModel):
    name = "RecipeThis"
    uses_logs = False
    default_model = "gemini-2.5-pro-exp-03-25"
    provider = "gemini"
