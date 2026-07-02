from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cameras_live import router as cameras_live_router
from app.api.photos import router as photos_router
from app.api.routes import router as api_router

app = FastAPI(title="Zaborsky ANPR", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(cameras_live_router, prefix="/api")
app.include_router(photos_router, prefix="/api")
