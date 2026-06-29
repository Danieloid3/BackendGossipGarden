import re

with open("app/schemas/chat.py", "r") as f:
    content = f.read()

content = content.replace(
    "audio_url: str | None = None",
    "audio_url: str | None = None\n    user_image_url: str | None = None"
)

with open("app/schemas/chat.py", "w") as f:
    f.write(content)
