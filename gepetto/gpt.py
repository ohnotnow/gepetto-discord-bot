from .base_model import BaseModel

class GPTModel(BaseModel):
    name = "Gepetto"
    uses_logs = True
    default_model = "gpt-4.1-mini"
    provider = "openai"
