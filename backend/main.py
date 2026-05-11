from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routes.trader import router as trader_router
from backend.routes.investor import router as investor_router
from backend.routes.chain import router as chain_router

app = FastAPI(
    title="AstroTrade API",
    description="Backend API for interacting with AstroTrade smart contracts.",
    version="0.1.0",
)

app.include_router(trader_router)
app.include_router(investor_router)
app.include_router(chain_router)

# Serve the frontend — must be mounted after all API routes
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
