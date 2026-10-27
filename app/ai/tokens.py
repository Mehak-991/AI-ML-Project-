"""Token counting with tiktoken, falling back to a flagged approximation.

tiktoken downloads its BPE files on first use of an encoding (about 2-4 MB each,
cached under TIKTOKEN_CACHE_DIR or the system temp dir). If tiktoken is not
installed or the download fails, counts are estimated as ceil(chars / 4) and
marked `approximate=True` rather than failing the request.
"""

import logging
import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DEFAULT_ENCODING = "o200k_base"
APPROX_CHARS_PER_TOKEN = 4
# Chat formatting overhead used by OpenAI's published counting recipe.
TOKENS_PER_MESSAGE = 3
TOKENS_REPLY_PRIMING = 3


class Encoding(Protocol):
    name: str

    def encode(self, text: str, *, disallowed_special: Any = ...) -> list[int]: ...


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    encoding: str
    approximate: bool


def load_tiktoken_encoding(model: str) -> Encoding | None:
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            return tiktoken.get_encoding(DEFAULT_ENCODING)
    except Exception as exc:  # network/download/cache failures
        logger.warning(
            "tiktoken encoding unavailable (%s); using approximation", type(exc).__name__
        )
        return None


class TokenCounter:
    def __init__(
        self,
        default_model: str,
        loader: Callable[[str], Encoding | None] = load_tiktoken_encoding,
    ) -> None:
        self.default_model = default_model
        self._loader = loader
        self._encodings: dict[str, Encoding | None] = {}
        self._lock = threading.Lock()

    def _encoding(self, model: str) -> Encoding | None:
        with self._lock:
            if model not in self._encodings:
                self._encodings[model] = self._loader(model)
            return self._encodings[model]

    def _count(self, text: str, encoding: Encoding | None) -> int:
        if encoding is None:
            return math.ceil(len(text) / APPROX_CHARS_PER_TOKEN)
        # Treat special-token text like "<|endoftext|>" as plain text instead of raising.
        return len(encoding.encode(text, disallowed_special=()))

    def count(self, text: str, model: str | None = None) -> TokenCount:
        encoding = self._encoding(model or self.default_model)
        return TokenCount(
            tokens=self._count(text, encoding),
            encoding=encoding.name if encoding else "approximate",
            approximate=encoding is None,
        )

    def count_messages(
        self, messages: Sequence[tuple[str, str]], model: str | None = None
    ) -> TokenCount:
        """Estimate prompt tokens for (role, content) chat messages."""
        encoding = self._encoding(model or self.default_model)
        total = TOKENS_REPLY_PRIMING + sum(
            TOKENS_PER_MESSAGE + self._count(role, encoding) + self._count(content, encoding)
            for role, content in messages
        )
        return TokenCount(
            tokens=total,
            encoding=encoding.name if encoding else "approximate",
            approximate=encoding is None,
        )

    def count_tokens(self, text: str) -> int:
        """Plain int length function (e.g. for text splitters)."""
        return self.count(text).tokens
