from .base_model import BaseModel

class ClaudeModel(BaseModel):
    name = "Minxie"
    uses_logs = False
    default_model = "claude-3-7-sonnet-20250219"
    provider = "anthropic"
