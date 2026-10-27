r"""Long-document analysis as a LangGraph state machine.

Concrete use: summarise text of any length and (optionally) score its sentiment.

    measure -> split -> summarize_chunks --(1 chunk)--> [classify] -> END
                                      \--(n chunks)--> combine -> [classify] -> END

LangGraph supplies the explicit, testable control flow (conditional routing,
typed state). The nodes call this project's own services (OpenAI chat, local
classifier, token counter, LangChain splitter), so there is no second LLM
client abstraction.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from app.ai.classification import LabelScore, TextClassificationService
from app.ai.llm import ChatMessage, ChatService
from app.ai.optional import require
from app.ai.text_splitting import split_text
from app.ai.tokens import TokenCounter
from app.core.exceptions import DataValidationError

SUMMARY_INSTRUCTIONS = (
    "Summarise the user's text in at most 5 sentences. Be factual, keep key numbers "
    "and names, and do not add information that is not in the text."
)
COMBINE_INSTRUCTIONS = (
    "The user provides summaries of consecutive parts of one document. Merge them into "
    "one coherent summary of at most 6 sentences without adding information."
)


@dataclass(frozen=True)
class TextAnalysisConfig:
    chunk_tokens: int = 2_000
    overlap_tokens: int = 100
    max_chunks: int = 10
    max_chars: int = 100_000
    summary_tokens: int = 600


class AnalysisState(TypedDict, total=False):
    text: str
    include_sentiment: bool
    token_count: int
    chunks: list[str]
    partial_summaries: list[str]
    summary: str
    sentiment: list[LabelScore] | None
    model: str


@dataclass(frozen=True)
class TextAnalysisResult:
    summary: str
    model: str
    token_count: int
    chunk_count: int
    sentiment: list[LabelScore] | None


class TextAnalysisWorkflow:
    def __init__(
        self,
        *,
        chat: ChatService,
        token_counter: TokenCounter,
        classifier_factory: Callable[[], TextClassificationService] | None = None,
        config: TextAnalysisConfig | None = None,
    ) -> None:
        self._chat = chat
        self._counter = token_counter
        self._classifier_factory = classifier_factory
        self.config = config or TextAnalysisConfig()
        self._graph = self._build()

    # --- nodes ---------------------------------------------------------------

    def _measure(self, state: AnalysisState) -> dict[str, Any]:
        return {"token_count": self._counter.count(state["text"]).tokens}

    def _split(self, state: AnalysisState) -> dict[str, Any]:
        if state["token_count"] <= self.config.chunk_tokens:
            return {"chunks": [state["text"]]}
        chunks = split_text(
            state["text"],
            chunk_tokens=self.config.chunk_tokens,
            overlap_tokens=self.config.overlap_tokens,
            length_function=self._counter.count_tokens,
        )
        if len(chunks) > self.config.max_chunks:
            raise DataValidationError(
                f"Text needs {len(chunks)} chunks; the limit is {self.config.max_chunks}."
            )
        return {"chunks": chunks}

    def _summarize(self, instructions: str, text: str) -> tuple[str, str]:
        result = self._chat.complete(
            [ChatMessage("system", instructions), ChatMessage("user", text)],
            max_output_tokens=self.config.summary_tokens,
        )
        return result.content.strip(), result.model

    def _summarize_chunks(self, state: AnalysisState) -> dict[str, Any]:
        summaries, model = [], self._chat.default_model
        for chunk in state["chunks"]:
            summary, model = self._summarize(SUMMARY_INSTRUCTIONS, chunk)
            summaries.append(summary)
        update: dict[str, Any] = {"partial_summaries": summaries, "model": model}
        if len(summaries) == 1:
            update["summary"] = summaries[0]
        return update

    def _combine(self, state: AnalysisState) -> dict[str, Any]:
        joined = "\n\n".join(
            f"Part {i}: {summary}" for i, summary in enumerate(state["partial_summaries"], 1)
        )
        summary, model = self._summarize(COMBINE_INSTRUCTIONS, joined)
        return {"summary": summary, "model": model}

    def _classify(self, state: AnalysisState) -> dict[str, Any]:
        classifier = self._classifier_factory()  # type: ignore[misc]
        # Classify the summary: it is short enough for the classifier's context window.
        result = classifier.classify([state["summary"][: classifier.max_chars]], top_k=2)
        return {"sentiment": result.labels[0]}

    # --- routing -------------------------------------------------------------

    def _wants_sentiment(self, state: AnalysisState) -> bool:
        return bool(state.get("include_sentiment")) and self._classifier_factory is not None

    def _after_summaries(self, state: AnalysisState) -> str:
        if len(state["partial_summaries"]) > 1:
            return "combine"
        return "classify" if self._wants_sentiment(state) else "end"

    def _after_combine(self, state: AnalysisState) -> str:
        return "classify" if self._wants_sentiment(state) else "end"

    def _build(self) -> Any:
        graph_module = require("langgraph.graph", "Text analysis workflow")
        graph = graph_module.StateGraph(AnalysisState)
        graph.add_node("measure", self._measure)
        graph.add_node("split", self._split)
        graph.add_node("summarize_chunks", self._summarize_chunks)
        graph.add_node("combine", self._combine)
        graph.add_node("classify", self._classify)
        graph.add_edge(graph_module.START, "measure")
        graph.add_edge("measure", "split")
        graph.add_edge("split", "summarize_chunks")
        graph.add_conditional_edges(
            "summarize_chunks",
            self._after_summaries,
            {"combine": "combine", "classify": "classify", "end": graph_module.END},
        )
        graph.add_conditional_edges(
            "combine", self._after_combine, {"classify": "classify", "end": graph_module.END}
        )
        graph.add_edge("classify", graph_module.END)
        return graph.compile()

    def run(self, text: str, *, include_sentiment: bool = True) -> TextAnalysisResult:
        if not text.strip():
            raise DataValidationError("Text must not be empty.")
        if len(text) > self.config.max_chars:
            raise DataValidationError(f"Text exceeds {self.config.max_chars} characters.")
        state = self._graph.invoke({"text": text, "include_sentiment": include_sentiment})
        return TextAnalysisResult(
            summary=state["summary"],
            model=state.get("model", self._chat.default_model),
            token_count=state["token_count"],
            chunk_count=len(state["chunks"]),
            sentiment=state.get("sentiment"),
        )
