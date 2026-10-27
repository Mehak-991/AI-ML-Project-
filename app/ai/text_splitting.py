"""Token-aware text chunking using LangChain's text splitters.

Concrete use: long documents must be split into chunks that fit an LLM or
embedding model's context window. LangChain's RecursiveCharacterTextSplitter
prefers paragraph/sentence boundaries; we measure length in real tokens.
(Also the chunking step a later RAG phase will reuse.)
"""

from collections.abc import Callable

from app.ai.optional import require


def split_text(
    text: str,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
    length_function: Callable[[str], int],
) -> list[str]:
    if chunk_tokens < 1 or not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError("Require chunk_tokens >= 1 and 0 <= overlap_tokens < chunk_tokens.")
    splitters = require("langchain_text_splitters", "Text splitting")
    splitter = splitters.RecursiveCharacterTextSplitter(
        chunk_size=chunk_tokens,
        chunk_overlap=overlap_tokens,
        length_function=length_function,
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]
