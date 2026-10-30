"""Aggregates all versioned API routers. Register new v1 route modules here."""

from fastapi import APIRouter

from app.api.routes import ai, datasets, deployments, health, models, monitoring, predictions
from app.schemas.common import ErrorResponse

# Errors any route can return (validation, middleware limits, unexpected/DB failures).
# Declaring them here documents the real {"error": {...}} envelope in OpenAPI instead of
# FastAPI's default {"detail": [...]} validation schema, which this API never returns.
COMMON_ERROR_RESPONSES: dict[int | str, dict] = {
    413: {"model": ErrorResponse, "description": "Request body too large"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded (see Retry-After)"},
    500: {"model": ErrorResponse, "description": "Unexpected server error (generic message)"},
    503: {"model": ErrorResponse, "description": "Dependency unavailable or not configured"},
}

api_v1_router = APIRouter(responses=COMMON_ERROR_RESPONSES)
api_v1_router.include_router(health.router)
api_v1_router.include_router(datasets.router)
api_v1_router.include_router(models.router)
api_v1_router.include_router(deployments.router)
api_v1_router.include_router(predictions.router)
api_v1_router.include_router(monitoring.router)
api_v1_router.include_router(ai.router)
