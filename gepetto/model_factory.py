from typing import Optional
from .base_model import BaseModel
from .gpt import GPTModel
from .claude import ClaudeModel
from .gemini import GeminiModel

def create_model(model_name: str) -> BaseModel:
    """Factory function to create appropriate model instance based on model name"""
    if model_name.startswith(('gpt-', 'o1-')):
        return GPTModel(model_name)
    elif model_name.startswith('claude-'):
        return ClaudeModel(model_name)
    elif model_name.startswith('gemini-'):
        return GeminiModel(model_name)
    else:
        raise ValueError(f"Unsupported model: {model_name}")
