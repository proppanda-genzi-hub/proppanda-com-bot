import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.endpoints import chat
from app.api.middleware import APIKeyMiddleware
from app.db.session import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()

# Initialize the App
app = FastAPI(
    title="Agentic Web Chatbot API",
    description="Multi-tenant Agentic Chatbot for Real Estate - Web Version",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API KEY MIDDLEWARE ---
app.add_middleware(APIKeyMiddleware)

# --- ROUTER REGISTRATION ---
app.include_router(
    chat.router, 
    prefix="/api/v1", 
    tags=["Chat"]
)

# --- ROOT ENDPOINT ---
@app.get("/")
async def health_check():
    return {
        "status": "active",
        "service": "Agentic Web Chatbot API",
        "version": "1.0.0"
    }

# --- ENTRY POINT ---
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
