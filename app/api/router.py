"""Aggregates all versioned API routers. Register new v1 route modules here."""

from fastapi import APIRouter

from app.api.routes import datasets, health, models

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)
api_v1_router.include_router(datasets.router)
api_v1_router.include_router(models.router)
