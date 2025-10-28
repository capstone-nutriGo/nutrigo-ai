import os

APP_NAME = "NutriGo AI"
APP_VERSION = os.getenv("MODEL_VERSION", "dev-0.0.1")
PORT = int(os.getenv("PORT", "8000"))
