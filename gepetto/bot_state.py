class BotState:
    def __init__(self):
        self.previous_image_description = "Here is my image based on recent chat in my Discord server!"
        self.previous_image_reasoning = "Dunno"
        self.previous_image_prompt = "Dunno"
        self.previous_image_themes = ""
        self.previous_reasoning_content = ""
        self.previous_themes = []
        self.horror_history = []
