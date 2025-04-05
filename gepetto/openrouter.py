import os
import json
from enum import Enum
import google.generativeai as genai
from gepetto.response import ChatResponse, FunctionResponse
from .base_model import BaseModel

class OpenrouterModel(BaseModel):
    name = "RecipeThis"
    uses_logs = True
    default_model = "quasar-alpha"
    provider = "openrouter"
