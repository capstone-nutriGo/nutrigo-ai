from fastapi import FastAPI
from .routes import health
from ..core.logging import setup_logging

setup_logging()
app = FastAPI(title="NutriGo AI")

app.include_router(health.router, prefix="/health", tags=["health"])
