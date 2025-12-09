from fastapi import FastAPI
from .routes import health
from ..core.logging import setup_logging
from nutrigo_ai.api.routes import nutrition, nutribot 

setup_logging()
app = FastAPI(title="NutriGo AI")

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(nutrition.router)
app.include_router(nutribot.router)
