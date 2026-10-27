"""Request/response schemas for embeddings, NLP, LLM chat and token counting.

Field limits here are hard upper bounds that protect the server. The stricter,
configurable limits (EMBEDDING_MAX_TEXTS, LLM_MAX_INPUT_TOKENS, ...) are
enforced by the services and also return 422.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HARD_MAX_TEXTS = 1_024
HARD_MAX_TEXT_CHARS = 200_000

Text = Annotated[str, StringConstraints(min_length=1, max_length=HARD_MAX_TEXT_CHARS)]
ModelName = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


# --- embeddings ---------------------------------------------------------------------


class EmbeddingRequest(StrictModel):
    texts: list[Text] = Field(min_length=1, max_length=HARD_MAX_TEXTS)
    normalize: bool = Field(default=True, description="L2-normalise vectors (cosine-ready).")


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float]


class EmbeddingResponse(StrictModel):
    model: str
    dimension: int
    count: int
    data: list[EmbeddingItem]


# --- classification -----------------------------------------------------------------


class ClassificationRequest(StrictModel):
    texts: list[Text] = Field(min_length=1, max_length=HARD_MAX_TEXTS)
    top_k: int = Field(default=1, ge=1, le=5)


class LabelScoreSchema(BaseModel):
    label: str
    score: float


class ClassificationItem(BaseModel):
    index: int
    labels: list[LabelScoreSchema]


class ClassificationResponse(StrictModel):
    model: str
    task: str
    results: list[ClassificationItem]


# --- chat ---------------------------------------------------------------------------


class ChatMessageSchema(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: Text


class ChatRequest(StrictModel):
    messages: list[ChatMessageSchema] = Field(min_length=1, max_length=500)
    model: ModelName | None = Field(
        default=None, description="Must be OPENAI_MODEL or listed in OPENAI_ALLOWED_MODELS."
    )
    max_output_tokens: int | None = Field(default=None, ge=16, le=32_768)
    temperature: float | None = Field(
        default=None, ge=0, le=2, description="Omit for reasoning models that reject it."
    )


class ChatUsageSchema(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatResponse(StrictModel):
    id: str
    model: str
    content: str
    finish_reason: str = Field(
        description="'stop', or why output ended early (e.g. 'max_output_tokens')."
    )
    usage: ChatUsageSchema | None


# --- tokens -------------------------------------------------------------------------


class TokenCountRequest(StrictModel):
    text: Annotated[str, StringConstraints(max_length=HARD_MAX_TEXT_CHARS)] | None = None
    messages: list[ChatMessageSchema] | None = Field(default=None, max_length=500)
    model: ModelName | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.text is None) == (self.messages is None):
            raise ValueError("Provide exactly one of 'text' or 'messages'.")
        return self


class TokenCountResponse(StrictModel):
    model: str
    encoding: str
    tokens: int
    approximate: bool = Field(description="True if tiktoken was unavailable (chars/4 estimate).")


# --- text analysis (LangGraph workflow) -----------------------------------------------


class TextAnalysisRequest(StrictModel):
    text: Text
    include_sentiment: bool = True


class TextAnalysisResponse(StrictModel):
    model: str
    summary: str
    token_count: int
    chunk_count: int
    sentiment: list[LabelScoreSchema] | None


# --- status -------------------------------------------------------------------------


class AIStatusResponse(BaseModel):
    packages: dict[str, bool]
    llm: dict[str, Any]
    embeddings: dict[str, Any]
    classifier: dict[str, Any]
    device_preference: str
    downloads_allowed: bool
    loaded_models: list[dict[str, Any]]
