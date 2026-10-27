"""LangGraph text-analysis workflow (fake LLM + fake classifier; no network)."""

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_text_splitters")

from app.ai.text_splitting import split_text
from app.ai.tokens import TokenCounter
from app.ai.workflows.text_analysis import TextAnalysisConfig, TextAnalysisWorkflow
from app.core.exceptions import DataValidationError
from tests.ai_fakes import FakeChat, FakeEncoding, fake_classifier

COUNTER = TokenCounter("fake", loader=lambda m: FakeEncoding())  # 1 token per word


def make_workflow(chat=None, *, with_classifier=True, **config) -> TextAnalysisWorkflow:
    return TextAnalysisWorkflow(
        chat=chat or FakeChat(),
        token_counter=COUNTER,
        classifier_factory=fake_classifier if with_classifier else None,
        config=TextAnalysisConfig(**({"chunk_tokens": 20, "overlap_tokens": 0} | config)),
    )


def paragraphs(n: int, words: int = 15) -> str:
    return "\n\n".join(" ".join(f"w{p}_{i}" for i in range(words)) for p in range(n))


def test_short_text_single_summary_and_sentiment() -> None:
    chat = FakeChat(reply="A good summary")
    result = make_workflow(chat).run("This is a short good text.")
    assert len(chat.calls) == 1
    assert chat.calls[0]["messages"][0].role == "system"
    assert result.chunk_count == 1
    assert result.summary == "A good summary #1"
    assert result.token_count == 6
    assert result.sentiment[0].label == "POSITIVE"


def test_long_text_is_split_summarised_and_combined() -> None:
    chat = FakeChat()
    result = make_workflow(chat).run(paragraphs(3))
    # 3 chunk summaries + 1 combine call
    assert result.chunk_count == 3
    assert len(chat.calls) == 4
    combine_input = chat.calls[-1]["messages"][1].content
    assert "Part 1:" in combine_input and "Part 3:" in combine_input
    assert result.summary.endswith("#4")


def test_sentiment_can_be_skipped() -> None:
    result = make_workflow(with_classifier=False).run("text", include_sentiment=True)
    assert result.sentiment is None
    assert make_workflow().run("text", include_sentiment=False).sentiment is None


def test_limits() -> None:
    with pytest.raises(DataValidationError, match="chunks"):
        make_workflow(max_chunks=2).run(paragraphs(5))
    with pytest.raises(DataValidationError, match="characters"):
        make_workflow(max_chars=10).run("x" * 11)
    with pytest.raises(DataValidationError, match="empty"):
        make_workflow().run("   ")


def test_split_text_respects_token_budget() -> None:
    chunks = split_text(
        paragraphs(4), chunk_tokens=20, overlap_tokens=0, length_function=COUNTER.count_tokens
    )
    assert len(chunks) == 4
    assert all(COUNTER.count_tokens(c) <= 20 for c in chunks)
    with pytest.raises(ValueError):
        split_text("x", chunk_tokens=10, overlap_tokens=10, length_function=len)
