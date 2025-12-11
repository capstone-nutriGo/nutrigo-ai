import os

APP_NAME = "NutriGo AI"
APP_VERSION = os.getenv("MODEL_VERSION", "dev-0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# S3 configuration (used for fetching uploaded images)
S3_BUCKET = os.getenv("S3_BUCKET")
S3_REGION = os.getenv("S3_REGION")
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_FORCE_PATH_STYLE = os.getenv("S3_FORCE_PATH_STYLE", "false").lower() == "true"