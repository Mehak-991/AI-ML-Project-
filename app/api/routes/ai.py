"""Embedding, NLP, LLM chat and token-counting endpoints.

Handlers are sync (`def`) so blocking model and provider calls run in FastAPI's
threadpool; local inference is additionally bounded by AI_INFERENCE_TIMEOUT_SECONDS
and provider calls by OPENAI_TIMEOUT_SECONDS.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.classification import TextClassificationService
from app.ai.embeddings import EmbeddingService
from app.ai.llm import ChatMessage, ChatService
from app.ai.tokens import TokenCounter
from app.api.deps import (
    AIServicesDep,
    SettingsDep,
    get_chat_service,
    get_embedding_service,
    get_text_classifier,
    get_token_counter,
)
from app.core.exceptions import DataValidationError
from app.schemas.ai import (
    AIStatusResponse,
    ChatRequest,
    ChatResponse,
    ClassificationItem,
    ClassificationRequest,
    ClassificationResponse,
    EmbeddingItem,
    EmbeddingRequest,
    EmbeddingResponse,
    LabelScoreSchema,
    TextAnalysisRequest,
    TextAnalysisResponse,
    TokenCountRequest,
    TokenCountResponse,
)
from app.schemas.common import ErrorResponse

router = APIRouter()


def _errors(*codes: int) -> dict:
    descriptions = {
        422: "Invalid input or limits exceeded",
        429: "Provider rate limit / quota (see Retry-After)",
        502: "Provider error",
        503: "Optional dependency missing, model failed to load, or provider not configured",
        504: "Inference or provider timeout",
    }
    return {c: {"model": ErrorResponse, "description": descriptions[c]} for c in codes}


@router.get("/ai/status", response_model=AIStatusResponse, tags=["ai"])
def ai_status(ai: AIServicesDep) -> AIStatusResponse:
    """Which optional AI packages are installed, provider configuration (never the key)."""
    return AIStatusResponse(**ai.status())


@router.post(
    "/embeddings",
    response_model=EmbeddingResponse,
    tags=["ai"],
    summary="Sentence embeddings",
    responses=_errors(422, 503, 504),
)
def create_embeddings(
    request: EmbeddingRequest,
    service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> EmbeddingResponse:
    result = service.embed(request.texts, normalize=request.normalize)
    return EmbeddingResponse(
        model=result.model,
        dimension=result.dimension,
        count=len(result.vectors),
        data=[EmbeddingItem(index=i, embedding=v) for i, v in enumerate(result.vectors)],
    )


@router.post(
    "/nlp/classify",
    response_model=ClassificationResponse,
    tags=["ai"],
    summary="Sentiment classification (transformer baseline)",
    responses=_errors(422, 503, 504),
)
def classify_texts(
    request: ClassificationRequest,
    service: Annotated[TextClassificationService, Depends(get_text_classifier)],
) -> ClassificationResponse:
    result = service.classify(request.texts, top_k=request.top_k)
    return ClassificationResponse(
        model=result.model,
        task=result.task,
        results=[
            ClassificationItem(
                index=i,
                labels=[LabelScoreSchema(label=x.label, score=x.score) for x in labels],
            )
            for i, labels in enumerate(result.labels)
        ],
    )


@router.post(
    "/llm/chat",
    response_model=ChatResponse,
    tags=["ai"],
    summary="LLM chat completion",
    responses=_errors(422, 429, 502, 503, 504),
)
def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    result = service.complete(
        [ChatMessage(m.role, m.content) for m in request.messages],
        model=request.model,
        max_output_tokens=request.max_output_tokens,
        temperature=request.temperature,
    )
    return ChatResponse(
        id=result.id,
        model=result.model,
        content=result.content,
        finish_reason=result.finish_reason,
        usage=result.usage.__dict__ if result.usage else None,
    )


@router.post(
    "/tokens/count",
    response_model=TokenCountResponse,
    tags=["ai"],
    summary="Count tokens for text or chat messages",
    responses=_errors(422),
)
def count_tokens(
    request: TokenCountRequest,
    counter: Annotated[TokenCounter, Depends(get_token_counter)],
    settings: SettingsDep,
) -> TokenCountResponse:
    total_chars = len(request.text or "") + sum(len(m.content) for m in request.messages or [])
    if total_chars > settings.TOKENIZER_MAX_TEXT_CHARS:
        raise DataValidationError(f"Input exceeds {settings.TOKENIZER_MAX_TEXT_CHARS} characters.")
    model = request.model or counter.default_model
    if request.messages is not None:
        counted = counter.count_messages([(m.role, m.content) for m in request.messages], model)
    else:
        counted = counter.count(request.text or "", model)
    return TokenCountResponse(
        model=model,
        encoding=counted.encoding,
        tokens=counted.tokens,
        approximate=counted.approximate,
    )


@router.post(
    "/nlp/analyze",
    response_model=TextAnalysisResponse,
    tags=["ai"],
    summary="Summarise (map-reduce for long text) and score sentiment — LangGraph workflow",
    responses=_errors(422, 429, 502, 503, 504),
)
def analyze_text(request: TextAnalysisRequest, ai: AIServicesDep) -> TextAnalysisResponse:
    workflow = ai.text_analysis(include_sentiment=request.include_sentiment)
    result = workflow.run(request.text, include_sentiment=request.include_sentiment)
    return TextAnalysisResponse(
        model=result.model,
        summary=result.summary,
        token_count=result.token_count,
        chunk_count=result.chunk_count,
        sentiment=[LabelScoreSchema(label=x.label, score=x.score) for x in result.sentiment]
        if result.sentiment
        else None,
    )
