from .base_model import BaseModel
import os
class GPTModel(BaseModel):
    name = "Gepetto"
    uses_logs = True
    default_model = os.getenv("BOT_MODEL", "gpt-4.1-mini")
    provider = "openai"
