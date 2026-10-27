"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.ai.classification import TextClassificationService
from app.ai.container import AIServices
from app.ai.embeddings import EmbeddingService
from app.ai.llm import ChatService
from app.ai.tokens import TokenCounter
from app.core.config import Settings, get_settings
from app.database.session import get_db

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]


def get_ai_services(request: Request) -> AIServices:
    return request.app.state.ai


AIServicesDep = Annotated[AIServices, Depends(get_ai_services)]


def get_embedding_service(ai: AIServicesDep) -> EmbeddingService:
    return ai.embedding_service


def get_text_classifier(ai: AIServicesDep) -> TextClassificationService:
    return ai.text_classification


def get_chat_service(ai: AIServicesDep) -> ChatService:
    return ai.chat_service()


def get_token_counter(ai: AIServicesDep) -> TokenCounter:
    return ai.token_counter
