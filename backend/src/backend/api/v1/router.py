from fastapi import APIRouter

from backend.api.v1 import auth, chat, health, topics

v1_router = APIRouter()
v1_router.include_router(health.router)
v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
v1_router.include_router(topics.router, prefix="/topics", tags=["topics"])
v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
